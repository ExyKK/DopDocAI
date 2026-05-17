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
}
