using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed record RepositoryRegistrationResult(RepositoryEntity Repository, bool Created);

public sealed record PagedRepositoryResult(
    IReadOnlyList<RepositoryEntity> Items,
    int TotalCount,
    int Limit,
    int Offset)
{
    public bool HasMore => Offset + Items.Count < TotalCount;
}
