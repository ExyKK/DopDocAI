using System.Diagnostics;
using DopDoc.ChatService.Domain;
using DopDoc.ChatService.Infrastructure.Clients;
using DopDoc.ChatService.Infrastructure.Data;
using DopDoc.ChatService.Infrastructure.Llm;
using DopDoc.Common.Errors;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Application.Chats;

public sealed class ChatApplicationService
{
    private const int MaxMessageLength = 50_000;
    private readonly ChatDbContext _db;
    private readonly RepositoryServiceClient _repositories;
    private readonly RetrievalServiceClient _retrieval;
    private readonly IChatCompletionProvider _llm;
    private readonly RetrievalOptions _retrievalOptions;
    private readonly LlmOptions _llmOptions;

    public ChatApplicationService(
        ChatDbContext db,
        RepositoryServiceClient repositories,
        RetrievalServiceClient retrieval,
        IChatCompletionProvider llm,
        IOptions<RetrievalOptions> retrievalOptions,
        IOptions<LlmOptions> llmOptions)
    {
        _db = db;
        _repositories = repositories;
        _retrieval = retrieval;
        _llm = llm;
        _retrievalOptions = retrievalOptions.Value;
        _llmOptions = llmOptions.Value;
    }

    public async Task<Chat> CreateAsync(Guid userId, CreateChatCommand command, CancellationToken ct)
    {
        ValidateCreateCommand(command);

        var snapshot = await _repositories.GetReadySnapshotAsync(
            userId,
            command.RepositoryId,
            command.SnapshotId,
            ct);
        var now = DateTimeOffset.UtcNow;

        var chat = new Chat
        {
            Id = Guid.NewGuid(),
            RepositoryId = snapshot.RepositoryId,
            SnapshotId = snapshot.Id,
            UserId = userId,
            Title = NormalizeTitle(command.Title),
            CreatedAt = now,
            UpdatedAt = now
        };

        _db.Chats.Add(chat);
        await _db.SaveChangesAsync(ct);

        return chat;
    }

    public async Task<PagedChatResult> ListAsync(
        Guid userId,
        Guid? repositoryId,
        ChatPagination pagination,
        CancellationToken ct)
    {
        var query = _db.Chats
            .AsNoTracking()
            .Where(x => x.UserId == userId && x.ArchivedAt == null);

        if (repositoryId is not null)
            query = query.Where(x => x.RepositoryId == repositoryId.Value);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(x => x.LastMessageAt ?? x.CreatedAt)
            .ThenByDescending(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedChatResult(items, total, pagination.Limit, pagination.Offset);
    }

    public async Task<Chat> GetAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var chat = await _db.Chats
            .AsNoTracking()
            .FirstOrDefaultAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        return chat ?? throw ChatNotFound(chatId);
    }

    public async Task<PagedChatMessageResult> ListMessagesAsync(
        Guid userId,
        Guid chatId,
        ChatPagination pagination,
        CancellationToken ct)
    {
        await EnsureChatExistsAsync(userId, chatId, ct);

        var query = _db.ChatMessages
            .AsNoTracking()
            .Where(x => x.ChatId == chatId);

        var total = await query.CountAsync(ct);
        var items = await query
            .Include(x => x.Sources.OrderBy(s => s.Ordinal))
            .OrderBy(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedChatMessageResult(items, total, pagination.Limit, pagination.Offset);
    }

    public async Task<SendChatMessageResult> SendMessageAsync(
        Guid userId,
        Guid chatId,
        SendChatMessageCommand command,
        CancellationToken ct)
    {
        var content = ValidateMessageContent(command.Content);
        var chat = await LoadChatForUpdateAsync(userId, chatId, ct);
        var history = await LoadHistoryAsync(chat.Id, _llmOptions.HistoryLimit, ct);

        var retrievalStopwatch = Stopwatch.StartNew();
        var retrievalResult = await _retrieval.SearchAsync(
            chat.SnapshotId,
            content,
            _retrievalOptions.TopK,
            _retrievalOptions.IncludeTests,
            _retrievalOptions.ScoreThreshold,
            ct);
        retrievalStopwatch.Stop();

        var promptSources = ChatPromptBuilder.BuildPromptSources(
            retrievalResult.Matches,
            _llmOptions.MaxSourceChars);

        var messages = BuildLlmMessages(content, history, promptSources);

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
        var userMessage = new ChatMessage
        {
            Id = Guid.NewGuid(),
            ChatId = chat.Id,
            Role = ChatRoles.User,
            ContentMarkdown = content,
            CreatedAt = now
        };

        var assistantMessage = new ChatMessage
        {
            Id = Guid.NewGuid(),
            ChatId = chat.Id,
            Role = ChatRoles.Assistant,
            ContentMarkdown = llmResponse.Content.Trim(),
            ModelName = llmResponse.Model,
            Provider = llmResponse.Provider,
            PromptVersion = ChatPromptBuilder.PromptVersion,
            InputTokens = llmResponse.PromptTokens,
            OutputTokens = llmResponse.CompletionTokens,
            FinishReason = llmResponse.FinishReason,
            RetrievalTimeMs = (int)Math.Min(int.MaxValue, retrievalStopwatch.ElapsedMilliseconds),
            GenerationTimeMs = (int)Math.Min(int.MaxValue, generationStopwatch.ElapsedMilliseconds),
            CreatedAt = now
        };

        var citedOrdinals = ChatPromptBuilder.ExtractCitedOrdinals(
            assistantMessage.ContentMarkdown,
            promptSources.Count);

        foreach (var source in promptSources)
        {
            assistantMessage.Sources.Add(
                ChatPromptBuilder.ToMessageSource(assistantMessage.Id, source, citedOrdinals));
        }

        chat.LastMessageAt = now;
        chat.UpdatedAt = now;
        chat.Title ??= GenerateTitle(content);

        _db.ChatMessages.Add(userMessage);
        _db.ChatMessages.Add(assistantMessage);
        await _db.SaveChangesAsync(ct);

        return new SendChatMessageResult(userMessage, assistantMessage);
    }

    private List<LlmChatMessage> BuildLlmMessages(
        string userContent,
        IReadOnlyList<ChatMessage> history,
        IReadOnlyList<PromptSource> promptSources)
    {
        var repositoryContext = ChatPromptBuilder.BuildRepositoryContext(promptSources);
        var messages = new List<LlmChatMessage>
        {
            new(ChatRoles.System, _llmOptions.DefaultSystemPrompt),
            new(ChatRoles.System, ChatPromptBuilder.BuildSourceRules(repositoryContext))
        };

        foreach (var message in history)
        {
            if (message.Role is ChatRoles.User or ChatRoles.Assistant)
                messages.Add(new LlmChatMessage(message.Role, message.ContentMarkdown));
        }

        messages.Add(new LlmChatMessage(ChatRoles.User, userContent));
        return messages;
    }

    private async Task EnsureChatExistsAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var exists = await _db.Chats
            .AsNoTracking()
            .AnyAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        if (!exists)
            throw ChatNotFound(chatId);
    }

    private async Task<Chat> LoadChatForUpdateAsync(Guid userId, Guid chatId, CancellationToken ct)
    {
        var chat = await _db.Chats
            .FirstOrDefaultAsync(x => x.Id == chatId && x.UserId == userId && x.ArchivedAt == null, ct);

        return chat ?? throw ChatNotFound(chatId);
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

    private static void ValidateCreateCommand(CreateChatCommand command)
    {
        if (command.RepositoryId == Guid.Empty)
            throw new ValidationException("repository_id is required", errorCode: "repository_id_required");

        if (command.SnapshotId == Guid.Empty)
            throw new ValidationException("snapshot_id is invalid", errorCode: "snapshot_id_invalid");

        if (NormalizeTitle(command.Title) is { Length: > 512 })
            throw new ValidationException("title is too long", errorCode: "chat_title_too_long");
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

    private static string? NormalizeTitle(string? title)
    {
        return string.IsNullOrWhiteSpace(title) ? null : title.Trim();
    }

    private static string GenerateTitle(string content)
    {
        var title = content.ReplaceLineEndings(" ").Trim();
        if (title.Length <= 80)
            return title;

        return title[..80].TrimEnd() + "...";
    }

    private static NotFoundException ChatNotFound(Guid chatId)
    {
        return new NotFoundException(
            $"Chat {chatId} was not found.",
            errorCode: "chat_not_found");
    }
}
