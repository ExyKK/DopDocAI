using System.Text.Json.Serialization;

namespace DopDoc.ChatService.Api.Contracts;

public sealed record CreateChatRequest(
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid? SnapshotId,
    [property: JsonPropertyName("title")] string? Title
);

public sealed record ChatResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("title")] string? Title,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt,
    [property: JsonPropertyName("last_message_at")] DateTimeOffset? LastMessageAt
);

public sealed record ChatListItemResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("title")] string? Title,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("last_message_at")] DateTimeOffset? LastMessageAt
);

public sealed record SendChatMessageRequest(
    [property: JsonPropertyName("content")] string? Content
);

public sealed record SendChatMessageResponse(
    [property: JsonPropertyName("user_message")] ChatMessageResponse UserMessage,
    [property: JsonPropertyName("assistant_message")] ChatMessageResponse AssistantMessage
);

public sealed record ChatMessageResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("chat_id")] Guid ChatId,
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content_markdown")] string ContentMarkdown,
    [property: JsonPropertyName("model_name")] string? ModelName,
    [property: JsonPropertyName("provider")] string? Provider,
    [property: JsonPropertyName("prompt_version")] string? PromptVersion,
    [property: JsonPropertyName("finish_reason")] string? FinishReason,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("sources")] IReadOnlyList<ChatMessageSourceResponse> Sources
);

public sealed record ChatMessageSourceResponse(
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("source_kind")] string SourceKind,
    [property: JsonPropertyName("file_path")] string? FilePath,
    [property: JsonPropertyName("symbol_name")] string? SymbolName,
    [property: JsonPropertyName("start_line")] int? StartLine,
    [property: JsonPropertyName("end_line")] int? EndLine,
    [property: JsonPropertyName("chunk_id")] string? ChunkId,
    [property: JsonPropertyName("score")] double? Score,
    [property: JsonPropertyName("used_in_answer")] bool UsedInAnswer,
    [property: JsonPropertyName("citation_label")] string? CitationLabel
);

public sealed record PagedResponse<TItem>(
    [property: JsonPropertyName("items")] IReadOnlyList<TItem> Items,
    [property: JsonPropertyName("limit")] int Limit,
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("has_more")] bool HasMore,
    [property: JsonPropertyName("total_count")] int TotalCount
);
