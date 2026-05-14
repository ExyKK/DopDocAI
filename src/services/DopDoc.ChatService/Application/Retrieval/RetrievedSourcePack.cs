namespace DopDoc.ChatService.Application.Retrieval;

public sealed record RetrievedSourcePack(
    Guid SnapshotId,
    string Query,
    IReadOnlyList<RetrievedSource> Sources
);

public sealed record RetrievedSource(
    int Ordinal,
    string ChunkId,
    double Score,
    string Text,
    RetrievedSourceLocation Location,
    RetrievedSourceEntity Entity
);

public sealed record RetrievedSourceLocation(
    Guid RepositoryId,
    Guid SnapshotId,
    string CommitSha,
    string FilePath,
    string Language,
    string SourceScope,
    bool IsTest,
    int? StartLine,
    int? EndLine,
    string? WorkspaceUnitId
);

public sealed record RetrievedSourceEntity(
    string Kind,
    string ChunkKind,
    string? Name,
    string? SymbolId,
    string? SymbolSignature
);

