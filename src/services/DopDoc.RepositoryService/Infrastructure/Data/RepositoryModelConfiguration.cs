using Microsoft.EntityFrameworkCore;

namespace DopDoc.RepositoryService.Infrastructure.Data;

internal static class RepositoryModelConfiguration
{
    public static void Configure(ModelBuilder modelBuilder, string schema)
    {
        modelBuilder.HasDefaultSchema(schema);

        modelBuilder.Entity<Domain.Repository>(builder =>
        {
            builder.ToTable("repositories");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.Provider).HasMaxLength(32).IsRequired();
            builder.Property(x => x.Host).HasMaxLength(128).IsRequired();
            builder.Property(x => x.Owner).HasMaxLength(128).IsRequired();
            builder.Property(x => x.Name).HasMaxLength(128).IsRequired();
            builder.Property(x => x.FullName).HasMaxLength(300).IsRequired();
            builder.Property(x => x.NormalizedUrl).IsRequired();
            builder.Property(x => x.DefaultBranch).HasMaxLength(256);
            builder.Property(x => x.SelectedBranch).HasMaxLength(256);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.UpdatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => x.NormalizedUrl).IsUnique();
            builder.HasIndex(x => x.FullName);
        });

        modelBuilder.Entity<Domain.UserRepository>(builder =>
        {
            builder.ToTable("user_repositories");
            builder.HasKey(x => new { x.UserId, x.RepositoryId });
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasOne(x => x.Repository)
                .WithMany(x => x.UserRepositories)
                .HasForeignKey(x => x.RepositoryId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.RepositorySnapshot>(builder =>
        {
            builder.ToTable("repository_snapshots");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.BranchName).HasMaxLength(256).IsRequired();
            builder.Property(x => x.CommitSha).HasMaxLength(64).IsRequired();
            builder.Property(x => x.TreeHash).HasMaxLength(128).IsRequired();
            builder.Property(x => x.CommitSubject).HasMaxLength(512);
            builder.Property(x => x.CommitAuthorName).HasMaxLength(256);
            builder.Property(x => x.CommitAuthorEmail).HasMaxLength(320);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.RepositoryId, x.CommitSha }).IsUnique();
            builder.HasIndex(x => new { x.RepositoryId, x.CreatedAt });
            builder.HasOne(x => x.Repository)
                .WithMany(x => x.Snapshots)
                .HasForeignKey(x => x.RepositoryId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.IndexRun>(builder =>
        {
            builder.ToTable("index_runs");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.TriggerKind).HasMaxLength(64).IsRequired();
            builder.Property(x => x.Status).HasMaxLength(64).IsRequired();
            builder.Property(x => x.Stage).HasMaxLength(64).IsRequired();
            builder.Property(x => x.WorkerId).HasMaxLength(256);
            builder.Property(x => x.ErrorCode).HasMaxLength(128);
            builder.Property(x => x.EmbeddingModel).HasMaxLength(256);
            builder.Property(x => x.StatsJson).HasColumnType("jsonb");
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.UpdatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.Status, x.LeaseUntil, x.CreatedAt });
            builder.HasIndex(x => new { x.RepositoryId, x.CreatedAt });
            builder.HasIndex(x => x.RepositoryId)
                .IsUnique()
                .HasDatabaseName("UX_index_runs_active_repository")
                .HasFilter("\"Status\" IN ('queued', 'running')");
            builder.HasOne(x => x.Repository)
                .WithMany(x => x.IndexRuns)
                .HasForeignKey(x => x.RepositoryId)
                .OnDelete(DeleteBehavior.Cascade);
            builder.HasOne(x => x.Snapshot)
                .WithMany(x => x.IndexRuns)
                .HasForeignKey(x => x.SnapshotId)
                .OnDelete(DeleteBehavior.SetNull);
        });

        modelBuilder.Entity<Domain.IndexRunEvent>(builder =>
        {
            builder.ToTable("index_run_events");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).UseIdentityByDefaultColumn();
            builder.Property(x => x.Level).HasMaxLength(32).IsRequired();
            builder.Property(x => x.Stage).HasMaxLength(64).IsRequired();
            builder.Property(x => x.Message).IsRequired();
            builder.Property(x => x.PayloadJson).HasColumnType("jsonb");
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.IndexRunId, x.Id });
            builder.HasOne(x => x.IndexRun)
                .WithMany(x => x.Events)
                .HasForeignKey(x => x.IndexRunId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.AnalysisArtifact>(builder =>
        {
            builder.ToTable("analysis_artifacts");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.ArtifactKind).HasMaxLength(128).IsRequired();
            builder.Property(x => x.StorageBucket).HasMaxLength(128).IsRequired();
            builder.Property(x => x.StorageKey).IsRequired();
            builder.Property(x => x.ContentType).HasMaxLength(256).IsRequired();
            builder.Property(x => x.Format).HasMaxLength(64).IsRequired();
            builder.Property(x => x.ChecksumSha256).HasMaxLength(64).IsRequired();
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.SnapshotId, x.ArtifactKind, x.SchemaVersion }).IsUnique();
            builder.HasIndex(x => new { x.SnapshotId, x.ArtifactKind });
            builder.HasOne(x => x.Snapshot)
                .WithMany(x => x.AnalysisArtifacts)
                .HasForeignKey(x => x.SnapshotId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.DocumentationRun>(builder =>
        {
            builder.ToTable("documentation_runs");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.TemplateKind).HasMaxLength(128).IsRequired();
            builder.Property(x => x.Status).HasMaxLength(64).IsRequired();
            builder.Property(x => x.Stage).HasMaxLength(64).IsRequired();
            builder.Property(x => x.WorkerId).HasMaxLength(256);
            builder.Property(x => x.ModelName).HasMaxLength(256);
            builder.Property(x => x.ErrorCode).HasMaxLength(128);
            builder.Property(x => x.VerificationSummaryJson).HasColumnType("jsonb");
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.UpdatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.Status, x.LeaseUntil, x.CreatedAt });
            builder.HasIndex(x => new { x.RepositoryId, x.SnapshotId, x.CreatedAt });
            builder.HasIndex(x => new { x.RepositoryId, x.SnapshotId, x.TemplateKind })
                .IsUnique()
                .HasDatabaseName("UX_documentation_runs_active_repository_snapshot_template")
                .HasFilter("\"Status\" IN ('queued', 'running')");
            builder.HasOne(x => x.Repository)
                .WithMany(x => x.DocumentationRuns)
                .HasForeignKey(x => x.RepositoryId)
                .OnDelete(DeleteBehavior.Cascade);
            builder.HasOne(x => x.Snapshot)
                .WithMany(x => x.DocumentationRuns)
                .HasForeignKey(x => x.SnapshotId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.DocumentationSection>(builder =>
        {
            builder.ToTable("documentation_sections");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.SectionKey).HasMaxLength(128).IsRequired();
            builder.Property(x => x.Title).HasMaxLength(256).IsRequired();
            builder.Property(x => x.Status).HasMaxLength(64).IsRequired();
            builder.Property(x => x.ConfidenceScore).HasPrecision(5, 4);
            builder.Property(x => x.VerificationReportJson).HasColumnType("jsonb");
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.UpdatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.DocumentationRunId, x.SectionKey }).IsUnique();
            builder.HasIndex(x => new { x.DocumentationRunId, x.Ordinal });
            builder.HasOne(x => x.DocumentationRun)
                .WithMany(x => x.Sections)
                .HasForeignKey(x => x.DocumentationRunId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.DocumentationSectionSource>(builder =>
        {
            builder.ToTable("documentation_section_sources");
            builder.HasKey(x => new { x.SectionId, x.Ordinal });
            builder.Property(x => x.SourceKind).HasMaxLength(64).IsRequired();
            builder.Property(x => x.FilePath).HasMaxLength(2048);
            builder.Property(x => x.SymbolName).HasMaxLength(512);
            builder.Property(x => x.ChunkId).HasMaxLength(256);
            builder.Property(x => x.Note).HasMaxLength(1024);
            builder.HasOne(x => x.Section)
                .WithMany(x => x.Sources)
                .HasForeignKey(x => x.SectionId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.DocumentationArtifact>(builder =>
        {
            builder.ToTable("documentation_artifacts");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.Attempt).IsRequired();
            builder.Property(x => x.ArtifactKind).HasMaxLength(128).IsRequired();
            builder.Property(x => x.StorageBucket).HasMaxLength(128).IsRequired();
            builder.Property(x => x.StorageKey).IsRequired();
            builder.Property(x => x.ContentType).HasMaxLength(256).IsRequired();
            builder.Property(x => x.Format).HasMaxLength(64).IsRequired();
            builder.Property(x => x.ChecksumSha256).HasMaxLength(64).IsRequired();
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.DocumentationRunId, x.Attempt, x.ArtifactKind });
            builder.HasIndex(x => x.SectionId);
            builder.HasOne(x => x.DocumentationRun)
                .WithMany(x => x.Artifacts)
                .HasForeignKey(x => x.DocumentationRunId)
                .OnDelete(DeleteBehavior.Cascade);
            builder.HasOne(x => x.Section)
                .WithMany(x => x.Artifacts)
                .HasForeignKey(x => x.SectionId)
                .OnDelete(DeleteBehavior.SetNull);
        });
    }
}
