namespace DopDoc.RepositoryService.Application.Jobs;

public sealed record CreateDocumentationRunCommand(
    Guid? SnapshotId,
    string? TemplateKind,
    Guid? BaseSnapshotId);
