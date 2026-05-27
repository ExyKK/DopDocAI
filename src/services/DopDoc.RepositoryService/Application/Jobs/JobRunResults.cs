using DopDoc.RepositoryService.Domain;

namespace DopDoc.RepositoryService.Application.Jobs;

public sealed record IndexRunCreateResult(IndexRun Run, bool Created);

public sealed record DocumentationRunCreateResult(DocumentationRun Run, bool Created);

public sealed record PagedIndexRunResult(
    IReadOnlyList<IndexRun> Items,
    int TotalCount,
    int Limit,
    int Offset)
{
    public bool HasMore => Offset + Items.Count < TotalCount;
}

public sealed record PagedDocumentationRunResult(
    IReadOnlyList<DocumentationRun> Items,
    int TotalCount,
    int Limit,
    int Offset)
{
    public bool HasMore => Offset + Items.Count < TotalCount;
}
