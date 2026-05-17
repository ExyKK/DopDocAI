using System.Text.Json.Serialization;

namespace DopDoc.RepositoryService.Api.Contracts;

public sealed record ReplaceDocumentationSectionsRequest(
    [property: JsonPropertyName("sections")] IReadOnlyList<DocumentationSectionPlanRequest> Sections
);

public sealed record DocumentationSectionPlanRequest(
    [property: JsonPropertyName("section_key")] string SectionKey,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("sources")] IReadOnlyList<DocumentationSectionSourceRequest> Sources
);

public sealed record DocumentationSectionSourceRequest(
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("source_kind")] string SourceKind,
    [property: JsonPropertyName("file_path")] string? FilePath,
    [property: JsonPropertyName("symbol_name")] string? SymbolName,
    [property: JsonPropertyName("start_line")] int? StartLine,
    [property: JsonPropertyName("end_line")] int? EndLine,
    [property: JsonPropertyName("chunk_id")] string? ChunkId,
    [property: JsonPropertyName("score")] double? Score,
    [property: JsonPropertyName("note")] string? Note
);

public sealed record DocumentationSectionResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("documentation_run_id")] Guid DocumentationRunId,
    [property: JsonPropertyName("section_key")] string SectionKey,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("source_count")] int SourceCount,
    [property: JsonPropertyName("sources")] IReadOnlyList<DocumentationSectionSourceResponse> Sources,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt
);

public sealed record DocumentationSectionSourceResponse(
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("source_kind")] string SourceKind,
    [property: JsonPropertyName("file_path")] string? FilePath,
    [property: JsonPropertyName("symbol_name")] string? SymbolName,
    [property: JsonPropertyName("start_line")] int? StartLine,
    [property: JsonPropertyName("end_line")] int? EndLine,
    [property: JsonPropertyName("chunk_id")] string? ChunkId,
    [property: JsonPropertyName("score")] double? Score,
    [property: JsonPropertyName("note")] string? Note
);
