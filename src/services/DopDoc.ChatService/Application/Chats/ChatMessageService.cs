using System.Diagnostics;
using DopDoc.ChatService.Application.Retrieval;
using DopDoc.ChatService.Domain;
using DopDoc.ChatService.Infrastructure.Clients;
using DopDoc.ChatService.Infrastructure.Data;
using DopDoc.ChatService.Infrastructure.Llm;
using DopDoc.Common.Errors;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Application.Chats;

public sealed class ChatMessageService
{
    private const int MaxMessageLength = 50_000;
    private readonly ChatDbContext _db;
    private readonly RetrievalServiceClient _retrieval;
    private readonly IChatCompletionProvider _llm;
    private readonly ChatPromptFactory _prompts;
    private readonly LlmOptions _llmOptions;

    public ChatMessageService(
        ChatDbContext db,
        RetrievalServiceClient retrieval,
        IChatCompletionProvider llm,
        ChatPromptFactory prompts,
        IOptions<LlmOptions> llmOptions)
    {
        _db = db;
        _retrieval = retrieval;
        _llm = llm;
        _prompts = prompts;
        _llmOptions = llmOptions.Value;
    }

    public async Task<SendChatMessageResult> SendAsync(
        Guid userId,
        Guid chatId,
        SendChatMessageCommand command,
        CancellationToken ct)
    {
        var content = ValidateMessageContent(command.Content);
        var chat = await LoadChatForUpdateAsync(userId, chatId, ct);
        var history = await LoadHistoryAsync(chat.Id, _llmOptions.HistoryLimit, ct);

        var retrievalStopwatch = Stopwatch.StartNew();
        RetrievedSourcePack retrieved = await _retrieval.SearchAsync(chat.SnapshotId, content, ct);
        retrievalStopwatch.Stop();

        var promptSources = _prompts.BuildPromptSources(retrieved.Sources, _llmOptions.MaxSourceChars);
        var messages = _prompts.BuildMessages(
            userContent: content,
            history: history,
            sources: promptSources,
            defaultSystemPrompt: _llmOptions.DefaultSystemPrompt);

        var generationStopwatch = Stopwatch.StartNew();
        var llmResponse = await _llm.GenerateAsync(messages, ct);
        generationStopwatch.Stop();

        if (string.IsNullOrWhiteSpace(llmResponse.Content))
        {
            throw new UpstreamServiceException(
                "LLM provider returned an empty response.",
                errorCode: "llm_response_empty");
        }

        var now = DateTimeOffset.UtcNow;
        var userMessage = CreateUserMessage(chat.Id, content, now);
        var assistantMessage = CreateAssistantMessage(
            chat.Id,
            llmResponse,
            retrievalStopwatch.ElapsedMilliseconds,
            generationStopwatch.ElapsedMilliseconds,
            now);

        var citedOrdinals = _prompts.ExtractCitedOrdinals(
            assistantMessage.ContentMarkdown,
            promptSources.Count);

        foreach (var source in promptSources)
            assistantMessage.Sources.Add(_prompts.ToMessageSource(assistantMessage.Id, source, citedOrdinals));

        chat.LastMessageAt = now;
        chat.UpdatedAt = now;
        chat.Title ??= GenerateTitle(content);

        _db.ChatMessages.Add(userMessage);
        _db.ChatMessages.Add(assistantMessage);
        await _db.SaveChangesAsync(ct);

        return new SendChatMessageResult(userMessage, assistantMessage);
    }

    private async Task<Chat> LoadChatForUpdateAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var chat = await _db.Chats
            .FirstOrDefaultAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        return chat ?? throw ChatErrors.NotFound(chatId);
    }

    private async Task<List<ChatMessage>> LoadHistoryAsync(Guid chatId, int limit, CancellationToken ct)
    {
        if (limit <= 0)
            return [];

        var items = await _db.ChatMessages
            .AsNoTracking()
            .Where(x => x.ChatId == chatId)
            .OrderByDescending(x => x.CreatedAt)
            .Take(limit)
            .ToListAsync(ct);

        items.Reverse();
        return items;
    }

    private static ChatMessage CreateUserMessage(Guid chatId, string content, DateTimeOffset now)
    {
        return new ChatMessage
        {
            Id = Guid.NewGuid(),
            ChatId = chatId,
            Role = ChatRoles.User,
            ContentMarkdown = content,
            CreatedAt = now
        };
    }

    private static ChatMessage CreateAssistantMessage(
        Guid chatId,
        ChatCompletionResult llmResponse,
        long retrievalTimeMs,
        long generationTimeMs,
        DateTimeOffset now)
    {
        return new ChatMessage
        {
            Id = Guid.NewGuid(),
            ChatId = chatId,
            Role = ChatRoles.Assistant,
            ContentMarkdown = llmResponse.Content.Trim(),
            ModelName = llmResponse.Model,
            Provider = llmResponse.Provider,
            PromptVersion = ChatPromptFactory.PromptVersion,
            InputTokens = llmResponse.PromptTokens,
            OutputTokens = llmResponse.CompletionTokens,
            FinishReason = llmResponse.FinishReason,
            RetrievalTimeMs = (int)Math.Min(int.MaxValue, retrievalTimeMs),
            GenerationTimeMs = (int)Math.Min(int.MaxValue, generationTimeMs),
            CreatedAt = now
        };
    }

    private static string ValidateMessageContent(string? content)
    {
        if (string.IsNullOrWhiteSpace(content))
            throw new ValidationException("content is required", errorCode: "chat_message_content_required");

        var normalized = content.Trim();
        if (normalized.Length > MaxMessageLength)
        {
            throw new ValidationException(
                $"content must be at most {MaxMessageLength} characters",
                errorCode: "chat_message_content_too_long");
        }

        return normalized;
    }

    private static string GenerateTitle(string content)
    {
        var title = content.ReplaceLineEndings(" ").Trim();
        if (title.Length <= 80)
            return title;

        return title[..80].TrimEnd() + "...";
    }
}

