namespace DopDoc.RepositoryService.Domain;

public sealed class DocumentationRun
{
    public Guid Id { get; set; }
    public Guid RepositoryId { get; set; }
    public Guid SnapshotId { get; set; }
    public Guid? SourceIndexRunId { get; set; }
    public Guid? BaseSnapshotId { get; set; }
    public Guid RequestedByUserId { get; set; }
    public string TemplateKind { get; set; } = "";
    public string Status { get; set; } = "";
    public string Stage { get; set; } = "";
    public int ProgressPct { get; set; }
    public int ProgressCurrent { get; set; }
    public int ProgressTotal { get; set; }
    public int Attempt { get; set; }
    public int MaxAttempts { get; set; }
    public string? WorkerId { get; set; }
    public DateTimeOffset? LeaseUntil { get; set; }
    public DateTimeOffset? HeartbeatAt { get; set; }
    public string? ModelName { get; set; }
    public string? ErrorCode { get; set; }
    public string? ErrorMessage { get; set; }
    public string? VerificationSummaryJson { get; set; }
    public Guid? PublishedManifestArtifactId { get; set; }
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? FinishedAt { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public Repository Repository { get; set; } = null!;
    public RepositorySnapshot Snapshot { get; set; } = null!;
    public ICollection<DocumentationSection> Sections { get; set; } = new List<DocumentationSection>();
    public ICollection<DocumentationArtifact> Artifacts { get; set; } = new List<DocumentationArtifact>();
}

public sealed class DocumentationSection
{
    public Guid Id { get; set; }
    public Guid DocumentationRunId { get; set; }
    public string SectionKey { get; set; } = "";
    public string Title { get; set; } = "";
    public int Ordinal { get; set; }
    public string Status { get; set; } = "";
    public int SourceCount { get; set; }
    public int UnsupportedClaims { get; set; }
    public decimal? ConfidenceScore { get; set; }
    public int? TokenInput { get; set; }
    public int? TokenOutput { get; set; }
    public Guid? ArtifactId { get; set; }
    public string? VerificationReportJson { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public DocumentationRun DocumentationRun { get; set; } = null!;
    public ICollection<DocumentationSectionSource> Sources { get; set; } = new List<DocumentationSectionSource>();
    public ICollection<DocumentationArtifact> Artifacts { get; set; } = new List<DocumentationArtifact>();
}

public sealed class DocumentationSectionSource
{
    public Guid SectionId { get; set; }
    public int Ordinal { get; set; }
    public Guid SnapshotId { get; set; }
    public string SourceKind { get; set; } = "";
    public string? FilePath { get; set; }
    public string? SymbolName { get; set; }
    public int? StartLine { get; set; }
    public int? EndLine { get; set; }
    public string? ChunkId { get; set; }
    public double? Score { get; set; }
    public string? Note { get; set; }

    public DocumentationSection Section { get; set; } = null!;
}

public sealed class DocumentationArtifact
{
    public Guid Id { get; set; }
    public Guid DocumentationRunId { get; set; }
    public Guid? SectionId { get; set; }
    public int Attempt { get; set; }
    public string ArtifactKind { get; set; } = "";
    public string StorageBucket { get; set; } = "";
    public string StorageKey { get; set; } = "";
    public string ContentType { get; set; } = "";
    public string Format { get; set; } = "";
    public string ChecksumSha256 { get; set; } = "";
    public long SizeBytes { get; set; }
    public int SchemaVersion { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public DocumentationRun DocumentationRun { get; set; } = null!;
    public DocumentationSection? Section { get; set; }
}
