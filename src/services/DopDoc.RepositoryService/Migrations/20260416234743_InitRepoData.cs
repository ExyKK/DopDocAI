using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace DopDoc.RepositoryService.Migrations
{
    /// <inheritdoc />
    public partial class InitRepoData : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql(@"CREATE SCHEMA IF NOT EXISTS repo;");
            migrationBuilder.Sql(@"CREATE EXTENSION IF NOT EXISTS pgcrypto;");
            
            migrationBuilder.EnsureSchema(
                name: "repo");

            migrationBuilder.CreateTable(
                name: "repositories",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    Provider = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Host = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Owner = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Name = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    FullName = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: false),
                    NormalizedUrl = table.Column<string>(type: "text", nullable: false),
                    DefaultBranch = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    SelectedBranch = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ActiveSnapshotId = table.Column<Guid>(type: "uuid", nullable: true),
                    CreatedByUserId = table.Column<Guid>(type: "uuid", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    ArchivedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_repositories", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "repository_snapshots",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    RepositoryId = table.Column<Guid>(type: "uuid", nullable: false),
                    BranchName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    CommitSha = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    TreeHash = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    CommitSubject = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: true),
                    CommitMessage = table.Column<string>(type: "text", nullable: true),
                    CommitAuthorName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CommitAuthorEmail = table.Column<string>(type: "character varying(320)", maxLength: 320, nullable: true),
                    CommitAuthoredAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    CommitCommittedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    FilesTotal = table.Column<int>(type: "integer", nullable: false),
                    GoFilesTotal = table.Column<int>(type: "integer", nullable: false),
                    ReadmeFilesTotal = table.Column<int>(type: "integer", nullable: false),
                    BytesTotal = table.Column<long>(type: "bigint", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_repository_snapshots", x => x.Id);
                    table.ForeignKey(
                        name: "FK_repository_snapshots_repositories_RepositoryId",
                        column: x => x.RepositoryId,
                        principalSchema: "repo",
                        principalTable: "repositories",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "user_repositories",
                schema: "repo",
                columns: table => new
                {
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    RepositoryId = table.Column<Guid>(type: "uuid", nullable: false),
                    Pinned = table.Column<bool>(type: "boolean", nullable: false),
                    LastViewedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_user_repositories", x => new { x.UserId, x.RepositoryId });
                    table.ForeignKey(
                        name: "FK_user_repositories_repositories_RepositoryId",
                        column: x => x.RepositoryId,
                        principalSchema: "repo",
                        principalTable: "repositories",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "analysis_artifacts",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: false),
                    ProducedByIndexRunId = table.Column<Guid>(type: "uuid", nullable: false),
                    ArtifactKind = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    StorageBucket = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    StorageKey = table.Column<string>(type: "text", nullable: false),
                    ContentType = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    Format = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    ChecksumSha256 = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    SizeBytes = table.Column<long>(type: "bigint", nullable: false),
                    RowCount = table.Column<int>(type: "integer", nullable: true),
                    SchemaVersion = table.Column<int>(type: "integer", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_analysis_artifacts", x => x.Id);
                    table.ForeignKey(
                        name: "FK_analysis_artifacts_repository_snapshots_SnapshotId",
                        column: x => x.SnapshotId,
                        principalSchema: "repo",
                        principalTable: "repository_snapshots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "documentation_runs",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    RepositoryId = table.Column<Guid>(type: "uuid", nullable: false),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: false),
                    SourceIndexRunId = table.Column<Guid>(type: "uuid", nullable: true),
                    BaseSnapshotId = table.Column<Guid>(type: "uuid", nullable: true),
                    RequestedByUserId = table.Column<Guid>(type: "uuid", nullable: false),
                    TemplateKind = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Status = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Stage = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    ProgressPct = table.Column<int>(type: "integer", nullable: false),
                    ProgressCurrent = table.Column<int>(type: "integer", nullable: false),
                    ProgressTotal = table.Column<int>(type: "integer", nullable: false),
                    Attempt = table.Column<int>(type: "integer", nullable: false),
                    MaxAttempts = table.Column<int>(type: "integer", nullable: false),
                    WorkerId = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    LeaseUntil = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    HeartbeatAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ModelName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ErrorCode = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    ErrorMessage = table.Column<string>(type: "text", nullable: true),
                    VerificationSummaryJson = table.Column<string>(type: "jsonb", nullable: true),
                    PublishedManifestArtifactId = table.Column<Guid>(type: "uuid", nullable: true),
                    StartedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    FinishedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_documentation_runs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_documentation_runs_repositories_RepositoryId",
                        column: x => x.RepositoryId,
                        principalSchema: "repo",
                        principalTable: "repositories",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_documentation_runs_repository_snapshots_SnapshotId",
                        column: x => x.SnapshotId,
                        principalSchema: "repo",
                        principalTable: "repository_snapshots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "index_runs",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    RepositoryId = table.Column<Guid>(type: "uuid", nullable: false),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: true),
                    RequestedByUserId = table.Column<Guid>(type: "uuid", nullable: false),
                    TriggerKind = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Status = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Stage = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    ProgressPct = table.Column<int>(type: "integer", nullable: false),
                    ProgressCurrent = table.Column<int>(type: "integer", nullable: false),
                    ProgressTotal = table.Column<int>(type: "integer", nullable: false),
                    Attempt = table.Column<int>(type: "integer", nullable: false),
                    MaxAttempts = table.Column<int>(type: "integer", nullable: false),
                    WorkerId = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    LeaseUntil = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    HeartbeatAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ErrorCode = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    ErrorMessage = table.Column<string>(type: "text", nullable: true),
                    EmbeddingModel = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    VectorSize = table.Column<int>(type: "integer", nullable: true),
                    FilesProcessed = table.Column<int>(type: "integer", nullable: false),
                    ChunksTotal = table.Column<int>(type: "integer", nullable: false),
                    SymbolsTotal = table.Column<int>(type: "integer", nullable: false),
                    VectorsUpserted = table.Column<int>(type: "integer", nullable: false),
                    StartedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    FinishedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    StatsJson = table.Column<string>(type: "jsonb", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_index_runs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_index_runs_repositories_RepositoryId",
                        column: x => x.RepositoryId,
                        principalSchema: "repo",
                        principalTable: "repositories",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_index_runs_repository_snapshots_SnapshotId",
                        column: x => x.SnapshotId,
                        principalSchema: "repo",
                        principalTable: "repository_snapshots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "documentation_sections",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    DocumentationRunId = table.Column<Guid>(type: "uuid", nullable: false),
                    SectionKey = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Title = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    Ordinal = table.Column<int>(type: "integer", nullable: false),
                    Status = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    SourceCount = table.Column<int>(type: "integer", nullable: false),
                    UnsupportedClaims = table.Column<int>(type: "integer", nullable: false),
                    ConfidenceScore = table.Column<decimal>(type: "numeric(5,4)", precision: 5, scale: 4, nullable: true),
                    TokenInput = table.Column<int>(type: "integer", nullable: true),
                    TokenOutput = table.Column<int>(type: "integer", nullable: true),
                    ArtifactId = table.Column<Guid>(type: "uuid", nullable: true),
                    VerificationReportJson = table.Column<string>(type: "jsonb", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_documentation_sections", x => x.Id);
                    table.ForeignKey(
                        name: "FK_documentation_sections_documentation_runs_DocumentationRunId",
                        column: x => x.DocumentationRunId,
                        principalSchema: "repo",
                        principalTable: "documentation_runs",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "index_run_events",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    IndexRunId = table.Column<Guid>(type: "uuid", nullable: false),
                    Level = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Stage = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Message = table.Column<string>(type: "text", nullable: false),
                    PayloadJson = table.Column<string>(type: "jsonb", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_index_run_events", x => x.Id);
                    table.ForeignKey(
                        name: "FK_index_run_events_index_runs_IndexRunId",
                        column: x => x.IndexRunId,
                        principalSchema: "repo",
                        principalTable: "index_runs",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "documentation_artifacts",
                schema: "repo",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    DocumentationRunId = table.Column<Guid>(type: "uuid", nullable: false),
                    SectionId = table.Column<Guid>(type: "uuid", nullable: true),
                    ArtifactKind = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    StorageBucket = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    StorageKey = table.Column<string>(type: "text", nullable: false),
                    ContentType = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    Format = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    ChecksumSha256 = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    SizeBytes = table.Column<long>(type: "bigint", nullable: false),
                    SchemaVersion = table.Column<int>(type: "integer", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_documentation_artifacts", x => x.Id);
                    table.ForeignKey(
                        name: "FK_documentation_artifacts_documentation_runs_DocumentationRun~",
                        column: x => x.DocumentationRunId,
                        principalSchema: "repo",
                        principalTable: "documentation_runs",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_documentation_artifacts_documentation_sections_SectionId",
                        column: x => x.SectionId,
                        principalSchema: "repo",
                        principalTable: "documentation_sections",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "documentation_section_sources",
                schema: "repo",
                columns: table => new
                {
                    SectionId = table.Column<Guid>(type: "uuid", nullable: false),
                    Ordinal = table.Column<int>(type: "integer", nullable: false),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: false),
                    SourceKind = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    FilePath = table.Column<string>(type: "character varying(2048)", maxLength: 2048, nullable: true),
                    SymbolName = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: true),
                    StartLine = table.Column<int>(type: "integer", nullable: true),
                    EndLine = table.Column<int>(type: "integer", nullable: true),
                    ChunkId = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    Score = table.Column<double>(type: "double precision", nullable: true),
                    Note = table.Column<string>(type: "character varying(1024)", maxLength: 1024, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_documentation_section_sources", x => new { x.SectionId, x.Ordinal });
                    table.ForeignKey(
                        name: "FK_documentation_section_sources_documentation_sections_Sectio~",
                        column: x => x.SectionId,
                        principalSchema: "repo",
                        principalTable: "documentation_sections",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_analysis_artifacts_SnapshotId_ArtifactKind",
                schema: "repo",
                table: "analysis_artifacts",
                columns: new[] { "SnapshotId", "ArtifactKind" });

            migrationBuilder.CreateIndex(
                name: "IX_analysis_artifacts_SnapshotId_ArtifactKind_SchemaVersion",
                schema: "repo",
                table: "analysis_artifacts",
                columns: new[] { "SnapshotId", "ArtifactKind", "SchemaVersion" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_documentation_artifacts_DocumentationRunId_ArtifactKind",
                schema: "repo",
                table: "documentation_artifacts",
                columns: new[] { "DocumentationRunId", "ArtifactKind" });

            migrationBuilder.CreateIndex(
                name: "IX_documentation_artifacts_SectionId",
                schema: "repo",
                table: "documentation_artifacts",
                column: "SectionId");

            migrationBuilder.CreateIndex(
                name: "IX_documentation_runs_RepositoryId_SnapshotId_CreatedAt",
                schema: "repo",
                table: "documentation_runs",
                columns: new[] { "RepositoryId", "SnapshotId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_documentation_runs_SnapshotId",
                schema: "repo",
                table: "documentation_runs",
                column: "SnapshotId");

            migrationBuilder.CreateIndex(
                name: "IX_documentation_runs_Status_LeaseUntil_CreatedAt",
                schema: "repo",
                table: "documentation_runs",
                columns: new[] { "Status", "LeaseUntil", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_documentation_sections_DocumentationRunId_Ordinal",
                schema: "repo",
                table: "documentation_sections",
                columns: new[] { "DocumentationRunId", "Ordinal" });

            migrationBuilder.CreateIndex(
                name: "IX_documentation_sections_DocumentationRunId_SectionKey",
                schema: "repo",
                table: "documentation_sections",
                columns: new[] { "DocumentationRunId", "SectionKey" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_index_run_events_IndexRunId_Id",
                schema: "repo",
                table: "index_run_events",
                columns: new[] { "IndexRunId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_index_runs_RepositoryId_CreatedAt",
                schema: "repo",
                table: "index_runs",
                columns: new[] { "RepositoryId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_index_runs_SnapshotId",
                schema: "repo",
                table: "index_runs",
                column: "SnapshotId");

            migrationBuilder.CreateIndex(
                name: "IX_index_runs_Status_LeaseUntil_CreatedAt",
                schema: "repo",
                table: "index_runs",
                columns: new[] { "Status", "LeaseUntil", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_repositories_FullName",
                schema: "repo",
                table: "repositories",
                column: "FullName");

            migrationBuilder.CreateIndex(
                name: "IX_repositories_NormalizedUrl",
                schema: "repo",
                table: "repositories",
                column: "NormalizedUrl",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_repository_snapshots_RepositoryId_CommitSha",
                schema: "repo",
                table: "repository_snapshots",
                columns: new[] { "RepositoryId", "CommitSha" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_repository_snapshots_RepositoryId_CreatedAt",
                schema: "repo",
                table: "repository_snapshots",
                columns: new[] { "RepositoryId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_user_repositories_RepositoryId",
                schema: "repo",
                table: "user_repositories",
                column: "RepositoryId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "analysis_artifacts",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "documentation_artifacts",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "documentation_section_sources",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "index_run_events",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "user_repositories",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "documentation_sections",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "index_runs",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "documentation_runs",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "repository_snapshots",
                schema: "repo");

            migrationBuilder.DropTable(
                name: "repositories",
                schema: "repo");
        }
    }
}
