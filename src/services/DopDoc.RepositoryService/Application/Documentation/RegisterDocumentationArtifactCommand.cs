namespace DopDoc.RepositoryService.Application.Documentation;

public sealed record RegisterDocumentationArtifactCommand(
    string ArtifactKind,
    string? SectionKey,
    string StorageBucket,
    string StorageKey,
    string ContentType,
    string Format,
    string ChecksumSha256,
    long SizeBytes,
    int SchemaVersion
);
