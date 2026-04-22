using DopDoc.RepositoryService.Domain;

namespace DopDoc.RepositoryService.Application.Jobs;

public sealed record IndexRunCreateResult(IndexRun Run, bool Created);

public sealed record DocumentationRunCreateResult(DocumentationRun Run, bool Created);
