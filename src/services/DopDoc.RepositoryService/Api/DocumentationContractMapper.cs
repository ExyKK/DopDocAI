using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Documentation;
using DopDoc.RepositoryService.Domain;

namespace DopDoc.RepositoryService.Api;

internal static class DocumentationContractMapper
{
    public static ReplaceDocumentationSectionsCommand ToCommand(ReplaceDocumentationSectionsRequest request)
    {
        return new ReplaceDocumentationSectionsCommand(
            Sections: request.Sections.Select(section => new DocumentationSectionPlanCommand(
                SectionKey: section.SectionKey,
                Title: section.Title,
                Ordinal: section.Ordinal,
                Status: section.Status,
                Sources: section.Sources.Select(source => new DocumentationSectionSourceCommand(
                    Ordinal: source.Ordinal,
                    SnapshotId: source.SnapshotId,
                    SourceKind: source.SourceKind,
                    FilePath: source.FilePath,
                    SymbolName: source.SymbolName,
                    StartLine: source.StartLine,
                    EndLine: source.EndLine,
                    ChunkId: source.ChunkId,
                    Score: source.Score,
                    Note: source.Note)).ToList())).ToList());
    }

    public static RegisterDocumentationArtifactCommand ToCommand(RegisterDocumentationArtifactRequest request)
    {
        return new RegisterDocumentationArtifactCommand(
            ArtifactKind: request.ArtifactKind,
            SectionKey: request.SectionKey,
            StorageBucket: request.StorageBucket,
            StorageKey: request.StorageKey,
            ContentType: request.ContentType,
            Format: request.Format,
            ChecksumSha256: request.ChecksumSha256,
            SizeBytes: request.SizeBytes,
            SchemaVersion: request.SchemaVersion);
    }

    public static DocumentationSectionResponse ToResponse(DocumentationSection section)
    {
        return new DocumentationSectionResponse(
            Id: section.Id,
            DocumentationRunId: section.DocumentationRunId,
            SectionKey: section.SectionKey,
            Title: section.Title,
            Ordinal: section.Ordinal,
            Status: section.Status,
            SourceCount: section.SourceCount,
            Sources: section.Sources
                .OrderBy(x => x.Ordinal)
                .Select(ToResponse)
                .ToList(),
            CreatedAt: section.CreatedAt,
            UpdatedAt: section.UpdatedAt);
    }

    private static DocumentationSectionSourceResponse ToResponse(DocumentationSectionSource source)
    {
        return new DocumentationSectionSourceResponse(
            Ordinal: source.Ordinal,
            SnapshotId: source.SnapshotId,
            SourceKind: source.SourceKind,
            FilePath: source.FilePath,
            SymbolName: source.SymbolName,
            StartLine: source.StartLine,
            EndLine: source.EndLine,
            ChunkId: source.ChunkId,
            Score: source.Score,
            Note: source.Note);
    }

    public static DocumentationArtifactResponse ToResponse(DocumentationArtifact artifact)
    {
        return new DocumentationArtifactResponse(
            Id: artifact.Id,
            DocumentationRunId: artifact.DocumentationRunId,
            SectionId: artifact.SectionId,
            ArtifactKind: artifact.ArtifactKind,
            StorageBucket: artifact.StorageBucket,
            StorageKey: artifact.StorageKey,
            ContentType: artifact.ContentType,
            Format: artifact.Format,
            ChecksumSha256: artifact.ChecksumSha256,
            SizeBytes: artifact.SizeBytes,
            SchemaVersion: artifact.SchemaVersion,
            CreatedAt: artifact.CreatedAt);
    }
}
