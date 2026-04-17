namespace DopDoc.RepositoryService.Domain;

public sealed class IndexRun
{
    public Guid Id { get; set; }
    public Guid RepositoryId { get; set; }
    public Guid? SnapshotId { get; set; }
    public Guid RequestedByUserId { get; set; }
    public string TriggerKind { get; set; } = "";
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
    public string? ErrorCode { get; set; }
    public string? ErrorMessage { get; set; }
    public string? EmbeddingModel { get; set; }
    public int? VectorSize { get; set; }
    public int FilesProcessed { get; set; }
    public int ChunksTotal { get; set; }
    public int SymbolsTotal { get; set; }
    public int VectorsUpserted { get; set; }
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? FinishedAt { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }
    public string? StatsJson { get; set; }

    public Repository Repository { get; set; } = null!;
    public RepositorySnapshot? Snapshot { get; set; }
    public ICollection<IndexRunEvent> Events { get; set; } = new List<IndexRunEvent>();
}

public sealed class IndexRunEvent
{
    public long Id { get; set; }
    public Guid IndexRunId { get; set; }
    public string Level { get; set; } = "";
    public string Stage { get; set; } = "";
    public string Message { get; set; } = "";
    public string? PayloadJson { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public IndexRun IndexRun { get; set; } = null!;
}

public sealed class AnalysisArtifact
{
    public Guid Id { get; set; }
    public Guid SnapshotId { get; set; }
    public Guid ProducedByIndexRunId { get; set; }
    public string ArtifactKind { get; set; } = "";
    public string StorageBucket { get; set; } = "";
    public string StorageKey { get; set; } = "";
    public string ContentType { get; set; } = "";
    public string Format { get; set; } = "";
    public string ChecksumSha256 { get; set; } = "";
    public long SizeBytes { get; set; }
    public int? RowCount { get; set; }
    public int SchemaVersion { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public RepositorySnapshot Snapshot { get; set; } = null!;
}
