using System.Text.Json.Serialization;

namespace DopDoc.ChatService.Infrastructure.Clients;

public sealed record RetrievalSearchRequest(
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("query")] string Query,
    [property: JsonPropertyName("top_k")] int TopK,
    [property: JsonPropertyName("filters")] RetrievalFilterRequest Filters,
    [property: JsonPropertyName("score_threshold")] double? ScoreThreshold
);

public sealed record RetrievalFilterRequest(
    [property: JsonPropertyName("workspace_unit_ids")] IReadOnlyList<string> WorkspaceUnitIds,
    [property: JsonPropertyName("languages")] IReadOnlyList<string> Languages,
    [property: JsonPropertyName("source_scopes")] IReadOnlyList<string> SourceScopes,
    [property: JsonPropertyName("chunk_kinds")] IReadOnlyList<string> ChunkKinds,
    [property: JsonPropertyName("package_ids")] IReadOnlyList<string> PackageIds,
    [property: JsonPropertyName("file_paths")] IReadOnlyList<string> FilePaths,
    [property: JsonPropertyName("include_tests")] bool IncludeTests
);

public sealed record RetrievalSearchResponse(
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("query")] string Query,
    [property: JsonPropertyName("top_k")] int TopK,
    [property: JsonPropertyName("elapsed_ms")] double ElapsedMs,
    [property: JsonPropertyName("embedding_provider")] string EmbeddingProvider,
    [property: JsonPropertyName("embedding_model")] string EmbeddingModel,
    [property: JsonPropertyName("hybrid")] RetrievalHybrid Hybrid,
    [property: JsonPropertyName("matches")] IReadOnlyList<RetrievalMatch> Matches
);

public sealed record RetrievalHybrid(
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("candidate_count")] int CandidateCount,
    [property: JsonPropertyName("query_terms")] IReadOnlyList<string> QueryTerms,
    [property: JsonPropertyName("path_hints")] IReadOnlyList<string> PathHints,
    [property: JsonPropertyName("symbol_hints")] IReadOnlyList<string> SymbolHints
);

public sealed record RetrievalMatch(
    [property: JsonPropertyName("chunk_id")] string ChunkId,
    [property: JsonPropertyName("score")] double Score,
    [property: JsonPropertyName("dense_score")] double DenseScore,
    [property: JsonPropertyName("score_breakdown")] RetrievalScoreBreakdown ScoreBreakdown,
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("source")] RetrievalSource Source,
    [property: JsonPropertyName("entity")] RetrievalEntity Entity
);

public sealed record RetrievalScoreBreakdown(
    [property: JsonPropertyName("dense")] double Dense,
    [property: JsonPropertyName("path")] double Path,
    [property: JsonPropertyName("symbol")] double Symbol,
    [property: JsonPropertyName("lexical")] double Lexical,
    [property: JsonPropertyName("total_boost")] double TotalBoost
);

public sealed record RetrievalSource(
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("commit_sha")] string CommitSha,
    [property: JsonPropertyName("file_path")] string FilePath,
    [property: JsonPropertyName("language")] string Language,
    [property: JsonPropertyName("source_scope")] string SourceScope,
    [property: JsonPropertyName("is_test")] bool IsTest,
    [property: JsonPropertyName("start_line")] int? StartLine,
    [property: JsonPropertyName("end_line")] int? EndLine,
    [property: JsonPropertyName("workspace_unit_id")] string? WorkspaceUnitId,
    [property: JsonPropertyName("package")] RetrievalPackage? Package
);

public sealed record RetrievalPackage(
    [property: JsonPropertyName("package_id")] string? PackageId,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("import_path")] string? ImportPath,
    [property: JsonPropertyName("dir_path")] string? DirPath,
    [property: JsonPropertyName("module_path")] string? ModulePath
);

public sealed record RetrievalEntity(
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("chunk_kind")] string ChunkKind,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("symbol_id")] string? SymbolId,
    [property: JsonPropertyName("symbol_signature")] string? SymbolSignature
);

