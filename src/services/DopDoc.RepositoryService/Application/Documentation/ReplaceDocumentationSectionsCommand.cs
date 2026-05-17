namespace DopDoc.RepositoryService.Application.Documentation;

public sealed record ReplaceDocumentationSectionsCommand(
    IReadOnlyList<DocumentationSectionPlanCommand> Sections
);

public sealed record DocumentationSectionPlanCommand(
    string SectionKey,
    string Title,
    int Ordinal,
    string Status,
    IReadOnlyList<DocumentationSectionSourceCommand> Sources
);

public sealed record DocumentationSectionSourceCommand(
    int Ordinal,
    Guid SnapshotId,
    string SourceKind,
    string? FilePath,
    string? SymbolName,
    int? StartLine,
    int? EndLine,
    string? ChunkId,
    double? Score,
    string? Note
);
