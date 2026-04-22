namespace DopDoc.RepositoryService.Application.Jobs;

public static class JobRunStages
{
    public static class Common
    {
        public const string Queued = "queued";
        public const string Finalizing = "finalizing";
        public const string Completed = "completed";
        public const string Failed = "failed";
        public const string Canceled = "canceled";
        public const string Stale = "stale";
    }

    public static class Index
    {
        public const string ResolvingRepository = "resolving_repository";
        public const string Cloning = "cloning";
        public const string ResolvingSnapshot = "resolving_snapshot";
        public const string CreatingSnapshot = "creating_snapshot";
        public const string ScanningFiles = "scanning_files";
        public const string Parsing = "parsing";
        public const string Embedding = "embedding";
        public const string UpsertingVectors = "upserting_vectors";
        public const string PublishingArtifacts = "publishing_artifacts";

        public static readonly IReadOnlySet<string> All = new HashSet<string>(StringComparer.Ordinal)
        {
            Common.Queued,
            ResolvingRepository,
            Cloning,
            ResolvingSnapshot,
            CreatingSnapshot,
            ScanningFiles,
            Parsing,
            Embedding,
            UpsertingVectors,
            PublishingArtifacts,
            Common.Finalizing,
            Common.Completed,
            Common.Failed,
            Common.Canceled,
            Common.Stale
        };
    }

    public static class Documentation
    {
        public const string LoadingProjectModel = "loading_project_model";
        public const string PlanningSections = "planning_sections";
        public const string RetrievingEvidence = "retrieving_evidence";
        public const string ExtractingFacts = "extracting_facts";
        public const string GeneratingSections = "generating_sections";
        public const string VerifyingSections = "verifying_sections";
        public const string PublishingArtifacts = "publishing_artifacts";

        public static readonly IReadOnlySet<string> All = new HashSet<string>(StringComparer.Ordinal)
        {
            Common.Queued,
            LoadingProjectModel,
            PlanningSections,
            RetrievingEvidence,
            ExtractingFacts,
            GeneratingSections,
            VerifyingSections,
            PublishingArtifacts,
            Common.Finalizing,
            Common.Completed,
            Common.Failed,
            Common.Canceled,
            Common.Stale
        };
    }

    public static bool IsKnownForKind(string kind, string? stage)
    {
        if (stage is null)
            return false;

        return kind switch
        {
            JobRunKinds.Index => Index.All.Contains(stage),
            JobRunKinds.Documentation => Documentation.All.Contains(stage),
            _ => false
        };
    }
}
