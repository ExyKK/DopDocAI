namespace DopDoc.RepositoryService.Application.Repositories;

public sealed record UpsertAnalysisArtifactCommand(
    Guid ProducedByIndexRunId,
    string ArtifactKind,
    string StorageBucket,
    string StorageKey,
    string ContentType,
    string Format,
    string ChecksumSha256,
    long SizeBytes,
    int? RowCount,
    int SchemaVersion
);
