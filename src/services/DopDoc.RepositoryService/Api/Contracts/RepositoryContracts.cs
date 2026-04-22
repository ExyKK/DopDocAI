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

public sealed record UpsertRepositorySnapshotRequest(
    [property: JsonPropertyName("branch_name")] string BranchName,
    [property: JsonPropertyName("commit_sha")] string CommitSha,
    [property: JsonPropertyName("tree_hash")] string TreeHash,
    [property: JsonPropertyName("commit_subject")] string? CommitSubject,
    [property: JsonPropertyName("commit_message")] string? CommitMessage,
    [property: JsonPropertyName("commit_author_name")] string? CommitAuthorName,
    [property: JsonPropertyName("commit_author_email")] string? CommitAuthorEmail,
    [property: JsonPropertyName("commit_authored_at")] DateTimeOffset? CommitAuthoredAt,
    [property: JsonPropertyName("commit_committed_at")] DateTimeOffset? CommitCommittedAt,
    [property: JsonPropertyName("files_total")] int FilesTotal,
    [property: JsonPropertyName("go_files_total")] int GoFilesTotal,
    [property: JsonPropertyName("readme_files_total")] int ReadmeFilesTotal,
    [property: JsonPropertyName("bytes_total")] long BytesTotal,
    [property: JsonPropertyName("set_active")] bool SetActive = true
);

public sealed record RepositorySnapshotResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("branch_name")] string BranchName,
    [property: JsonPropertyName("commit_sha")] string CommitSha,
    [property: JsonPropertyName("tree_hash")] string TreeHash,
    [property: JsonPropertyName("commit_subject")] string? CommitSubject,
    [property: JsonPropertyName("commit_message")] string? CommitMessage,
    [property: JsonPropertyName("commit_author_name")] string? CommitAuthorName,
    [property: JsonPropertyName("commit_author_email")] string? CommitAuthorEmail,
    [property: JsonPropertyName("commit_authored_at")] DateTimeOffset? CommitAuthoredAt,
    [property: JsonPropertyName("commit_committed_at")] DateTimeOffset? CommitCommittedAt,
    [property: JsonPropertyName("files_total")] int FilesTotal,
    [property: JsonPropertyName("go_files_total")] int GoFilesTotal,
    [property: JsonPropertyName("readme_files_total")] int ReadmeFilesTotal,
    [property: JsonPropertyName("bytes_total")] long BytesTotal,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt
);

public sealed record PagedResponse<TItem>(
    [property: JsonPropertyName("items")] IReadOnlyList<TItem> Items,
    [property: JsonPropertyName("limit")] int Limit,
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("has_more")] bool HasMore,
    [property: JsonPropertyName("total_count")] int TotalCount
);
