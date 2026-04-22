using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;
using RepositorySnapshotEntity = DopDoc.RepositoryService.Domain.RepositorySnapshot;

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

public sealed record RepositorySnapshotUpsertResult(RepositorySnapshotEntity Snapshot, bool Created);

public sealed record PagedRepositorySnapshotResult(
    IReadOnlyList<RepositorySnapshotEntity> Items,
    int TotalCount,
    int Limit,
    int Offset)
{
    public bool HasMore => Offset + Items.Count < TotalCount;
}
