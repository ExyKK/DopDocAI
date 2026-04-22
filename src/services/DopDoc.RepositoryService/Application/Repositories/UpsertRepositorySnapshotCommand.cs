namespace DopDoc.RepositoryService.Application.Repositories;

public sealed record UpsertRepositorySnapshotCommand(
    string BranchName,
    string CommitSha,
    string TreeHash,
    string? CommitSubject,
    string? CommitMessage,
    string? CommitAuthorName,
    string? CommitAuthorEmail,
    DateTimeOffset? CommitAuthoredAt,
    DateTimeOffset? CommitCommittedAt,
    int FilesTotal,
    int GoFilesTotal,
    int ReadmeFilesTotal,
    long BytesTotal,
    bool SetActive = true);
