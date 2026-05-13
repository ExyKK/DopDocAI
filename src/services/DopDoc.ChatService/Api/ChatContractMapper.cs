using DopDoc.ChatService.Api.Contracts;
using DopDoc.ChatService.Application.Chats;
using DopDoc.ChatService.Domain;

namespace DopDoc.ChatService.Api;

public static class ChatContractMapper
{
    public static CreateChatCommand ToCommand(CreateChatRequest request)
    {
        return new CreateChatCommand(
            RepositoryId: request.RepositoryId,
            SnapshotId: request.SnapshotId,
            Title: request.Title);
    }

    public static SendChatMessageCommand ToCommand(SendChatMessageRequest request)
    {
        return new SendChatMessageCommand(request.Content);
    }

    public static ChatResponse ToResponse(Chat chat)
    {
        return new ChatResponse(
            Id: chat.Id,
            RepositoryId: chat.RepositoryId,
            SnapshotId: chat.SnapshotId,
            Title: chat.Title,
            CreatedAt: chat.CreatedAt,
            UpdatedAt: chat.UpdatedAt,
            LastMessageAt: chat.LastMessageAt);
    }

    public static ChatListItemResponse ToListItem(Chat chat)
    {
        return new ChatListItemResponse(
            Id: chat.Id,
            RepositoryId: chat.RepositoryId,
            SnapshotId: chat.SnapshotId,
            Title: chat.Title,
            CreatedAt: chat.CreatedAt,
            LastMessageAt: chat.LastMessageAt);
    }

    public static PagedResponse<ChatListItemResponse> ToPagedResponse(PagedChatResult page)
    {
        return new PagedResponse<ChatListItemResponse>(
            Items: page.Items.Select(ToListItem).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.Offset + page.Items.Count < page.TotalCount,
            TotalCount: page.TotalCount);
    }

    public static PagedResponse<ChatMessageResponse> ToPagedResponse(PagedChatMessageResult page)
    {
        return new PagedResponse<ChatMessageResponse>(
            Items: page.Items.Select(ToResponse).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.Offset + page.Items.Count < page.TotalCount,
            TotalCount: page.TotalCount);
    }

    public static SendChatMessageResponse ToResponse(SendChatMessageResult result)
    {
        return new SendChatMessageResponse(
            UserMessage: ToResponse(result.UserMessage),
            AssistantMessage: ToResponse(result.AssistantMessage));
    }

    public static ChatMessageResponse ToResponse(ChatMessage message)
    {
        return new ChatMessageResponse(
            Id: message.Id,
            ChatId: message.ChatId,
            Role: message.Role,
            ContentMarkdown: message.ContentMarkdown,
            ModelName: message.ModelName,
            Provider: message.Provider,
            PromptVersion: message.PromptVersion,
            FinishReason: message.FinishReason,
            CreatedAt: message.CreatedAt,
            Sources: message.Sources
                .OrderBy(x => x.Ordinal)
                .Select(ToResponse)
                .ToList());
    }

    private static ChatMessageSourceResponse ToResponse(ChatMessageSource source)
    {
        return new ChatMessageSourceResponse(
            Ordinal: source.Ordinal,
            SnapshotId: source.SnapshotId,
            SourceKind: source.SourceKind,
            FilePath: source.FilePath,
            SymbolName: source.SymbolName,
            StartLine: source.StartLine,
            EndLine: source.EndLine,
            ChunkId: source.ChunkId,
            Score: source.Score,
            UsedInAnswer: source.UsedInAnswer,
            CitationLabel: source.CitationLabel);
    }
}

