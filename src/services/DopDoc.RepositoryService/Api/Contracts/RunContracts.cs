using System.Text.Json.Serialization;

namespace DopDoc.RepositoryService.Api.Contracts;

public sealed record CreateDocumentationRunRequest(
    [property: JsonPropertyName("snapshot_id")] Guid? SnapshotId,
    [property: JsonPropertyName("template_kind")] string? TemplateKind,
    [property: JsonPropertyName("base_snapshot_id")] Guid? BaseSnapshotId
);

public sealed record RunAcceptedResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("stage")] string Stage,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid? SnapshotId,
    [property: JsonPropertyName("status_url")] string StatusUrl,
    [property: JsonPropertyName("stream_url")] string StreamUrl
);

public sealed record IndexRunResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid? SnapshotId,
    [property: JsonPropertyName("trigger_kind")] string TriggerKind,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("stage")] string Stage,
    [property: JsonPropertyName("progress_pct")] int ProgressPct,
    [property: JsonPropertyName("progress_current")] int ProgressCurrent,
    [property: JsonPropertyName("progress_total")] int ProgressTotal,
    [property: JsonPropertyName("attempt")] int Attempt,
    [property: JsonPropertyName("max_attempts")] int MaxAttempts,
    [property: JsonPropertyName("error_code")] string? ErrorCode,
    [property: JsonPropertyName("error_message")] string? ErrorMessage,
    [property: JsonPropertyName("embedding_model")] string? EmbeddingModel,
    [property: JsonPropertyName("vector_size")] int? VectorSize,
    [property: JsonPropertyName("files_processed")] int FilesProcessed,
    [property: JsonPropertyName("chunks_total")] int ChunksTotal,
    [property: JsonPropertyName("symbols_total")] int SymbolsTotal,
    [property: JsonPropertyName("vectors_upserted")] int VectorsUpserted,
    [property: JsonPropertyName("started_at")] DateTimeOffset? StartedAt,
    [property: JsonPropertyName("finished_at")] DateTimeOffset? FinishedAt,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt
);

public sealed record DocumentationRunResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("source_index_run_id")] Guid? SourceIndexRunId,
    [property: JsonPropertyName("base_snapshot_id")] Guid? BaseSnapshotId,
    [property: JsonPropertyName("template_kind")] string TemplateKind,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("stage")] string Stage,
    [property: JsonPropertyName("progress_pct")] int ProgressPct,
    [property: JsonPropertyName("progress_current")] int ProgressCurrent,
    [property: JsonPropertyName("progress_total")] int ProgressTotal,
    [property: JsonPropertyName("attempt")] int Attempt,
    [property: JsonPropertyName("max_attempts")] int MaxAttempts,
    [property: JsonPropertyName("model_name")] string? ModelName,
    [property: JsonPropertyName("error_code")] string? ErrorCode,
    [property: JsonPropertyName("error_message")] string? ErrorMessage,
    [property: JsonPropertyName("published_manifest_artifact_id")] Guid? PublishedManifestArtifactId,
    [property: JsonPropertyName("started_at")] DateTimeOffset? StartedAt,
    [property: JsonPropertyName("finished_at")] DateTimeOffset? FinishedAt,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt
);
