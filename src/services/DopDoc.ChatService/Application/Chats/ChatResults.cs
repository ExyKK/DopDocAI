using DopDoc.ChatService.Domain;

namespace DopDoc.ChatService.Application.Chats;

public sealed record CreateChatCommand(
    Guid RepositoryId,
    Guid? SnapshotId,
    string? Title
);

public sealed record SendChatMessageCommand(string? Content);

public sealed record PagedChatResult(
    IReadOnlyList<Chat> Items,
    int TotalCount,
    int Limit,
    int Offset
);

public sealed record PagedChatMessageResult(
    IReadOnlyList<ChatMessage> Items,
    int TotalCount,
    int Limit,
    int Offset
);

public sealed record SendChatMessageResult(
    ChatMessage UserMessage,
    ChatMessage AssistantMessage
);
