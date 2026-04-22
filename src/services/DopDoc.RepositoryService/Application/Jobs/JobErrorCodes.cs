namespace DopDoc.RepositoryService.Application.Jobs;

public static class JobErrorCodes
{
    public const string Unknown = "unknown_error";
    public const string ValidationFailed = "validation_failed";
    public const string RepositoryNotFound = "repository_not_found";
    public const string RepositoryCloneFailed = "repository_clone_failed";
    public const string RepositoryResolveFailed = "repository_resolve_failed";
    public const string SnapshotConflict = "snapshot_conflict";
    public const string WorkerLeaseLost = "worker_lease_lost";
    public const string WorkerHeartbeatLost = "worker_heartbeat_lost";
    public const string Timeout = "timeout";
    public const string ArtifactPublishFailed = "artifact_publish_failed";
    public const string EmbeddingFailed = "embedding_failed";
    public const string VectorUpsertFailed = "vector_upsert_failed";
    public const string LlmProviderUnavailable = "llm_provider_unavailable";
    public const string VerificationFailed = "verification_failed";
    public const string CanceledByUser = "canceled_by_user";
    public const string StaleLeaseExpired = "stale_lease_expired";
    public const string TransientInfrastructureFailure = "transient_infrastructure_failure";

    public static readonly IReadOnlySet<string> All = new HashSet<string>(StringComparer.Ordinal)
    {
        Unknown,
        ValidationFailed,
        RepositoryNotFound,
        RepositoryCloneFailed,
        RepositoryResolveFailed,
        SnapshotConflict,
        WorkerLeaseLost,
        WorkerHeartbeatLost,
        Timeout,
        ArtifactPublishFailed,
        EmbeddingFailed,
        VectorUpsertFailed,
        LlmProviderUnavailable,
        VerificationFailed,
        CanceledByUser,
        StaleLeaseExpired,
        TransientInfrastructureFailure
    };
}
