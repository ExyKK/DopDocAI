namespace DopDoc.RepositoryService.Domain;

public sealed class Repository
{
    public Guid Id { get; set; }
    public string Provider { get; set; } = "";
    public string Host { get; set; } = "";
    public string Owner { get; set; } = "";
    public string Name { get; set; } = "";
    public string FullName { get; set; } = "";
    public string NormalizedUrl { get; set; } = "";
    public string? DefaultBranch { get; set; }
    public string? SelectedBranch { get; set; }
    public Guid? ActiveSnapshotId { get; set; }
    public Guid CreatedByUserId { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }
    public DateTimeOffset? ArchivedAt { get; set; }

    public ICollection<UserRepository> UserRepositories { get; set; } = new List<UserRepository>();
    public ICollection<RepositorySnapshot> Snapshots { get; set; } = new List<RepositorySnapshot>();
    public ICollection<IndexRun> IndexRuns { get; set; } = new List<IndexRun>();
    public ICollection<DocumentationRun> DocumentationRuns { get; set; } = new List<DocumentationRun>();
}

public sealed class UserRepository
{
    public Guid UserId { get; set; }
    public Guid RepositoryId { get; set; }
    public bool Pinned { get; set; }
    public DateTimeOffset? LastViewedAt { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public Repository Repository { get; set; } = null!;
}

public sealed class RepositorySnapshot
{
    public Guid Id { get; set; }
    public Guid RepositoryId { get; set; }
    public string BranchName { get; set; } = "";
    public string CommitSha { get; set; } = "";
    public string TreeHash { get; set; } = "";
    public string? CommitSubject { get; set; }
    public string? CommitMessage { get; set; }
    public string? CommitAuthorName { get; set; }
    public string? CommitAuthorEmail { get; set; }
    public DateTimeOffset? CommitAuthoredAt { get; set; }
    public DateTimeOffset? CommitCommittedAt { get; set; }
    public int FilesTotal { get; set; }
    public int GoFilesTotal { get; set; }
    public int ReadmeFilesTotal { get; set; }
    public long BytesTotal { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public Repository Repository { get; set; } = null!;
    public ICollection<IndexRun> IndexRuns { get; set; } = new List<IndexRun>();
    public ICollection<AnalysisArtifact> AnalysisArtifacts { get; set; } = new List<AnalysisArtifact>();
    public ICollection<DocumentationRun> DocumentationRuns { get; set; } = new List<DocumentationRun>();
}
