namespace DopDoc.ChatService.Application.Snapshots;

public sealed record ReadySnapshotRef(
    Guid RepositoryId,
    Guid SnapshotId,
    string CommitSha
);

