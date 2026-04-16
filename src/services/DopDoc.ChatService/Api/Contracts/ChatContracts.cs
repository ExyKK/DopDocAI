using System.Text.Json.Serialization;

namespace DopDoc.ChatService.Api.Contracts;

public sealed record ChatListItemResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("title")] string? Title,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("last_message_at")] DateTimeOffset? LastMessageAt
);

public sealed record PagedResponse<TItem>(
    [property: JsonPropertyName("items")] IReadOnlyList<TItem> Items,
    [property: JsonPropertyName("limit")] int Limit,
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("has_more")] bool HasMore,
    [property: JsonPropertyName("total_count")] int TotalCount
);
