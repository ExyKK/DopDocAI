using System.Text.Json.Serialization;

namespace DopDoc.RepositoryService.Api.Contracts;

public sealed record IndexRepositoryRequest(
    [property: JsonPropertyName("repository_url")] string RepositoryUrl,
    [property: JsonPropertyName("selected_branch")] string? SelectedBranch
);

public sealed record RepositoryListItemResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("full_name")] string FullName,
    [property: JsonPropertyName("selected_branch")] string? SelectedBranch,
    [property: JsonPropertyName("default_branch")] string? DefaultBranch,
    [property: JsonPropertyName("active_snapshot_id")] Guid? ActiveSnapshotId,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt
);

public sealed record RepositoryResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("provider")] string Provider,
    [property: JsonPropertyName("host")] string Host,
    [property: JsonPropertyName("owner")] string Owner,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("full_name")] string FullName,
    [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("selected_branch")] string? SelectedBranch,
    [property: JsonPropertyName("default_branch")] string? DefaultBranch,
    [property: JsonPropertyName("active_snapshot_id")] Guid? ActiveSnapshotId,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt
);

public sealed record PagedResponse<TItem>(
    [property: JsonPropertyName("items")] IReadOnlyList<TItem> Items,
    [property: JsonPropertyName("limit")] int Limit,
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("has_more")] bool HasMore,
    [property: JsonPropertyName("total_count")] int TotalCount
);
