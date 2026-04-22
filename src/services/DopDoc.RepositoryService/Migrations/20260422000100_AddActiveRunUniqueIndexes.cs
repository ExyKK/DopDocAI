using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DopDoc.RepositoryService.Migrations
{
    /// <inheritdoc />
    public partial class AddActiveRunUniqueIndexes : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateIndex(
                name: "UX_documentation_runs_active_repository_snapshot_template",
                schema: "repo",
                table: "documentation_runs",
                columns: new[] { "RepositoryId", "SnapshotId", "TemplateKind" },
                unique: true,
                filter: "\"Status\" IN ('queued', 'running')");

            migrationBuilder.CreateIndex(
                name: "UX_index_runs_active_repository",
                schema: "repo",
                table: "index_runs",
                column: "RepositoryId",
                unique: true,
                filter: "\"Status\" IN ('queued', 'running')");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "UX_documentation_runs_active_repository_snapshot_template",
                schema: "repo",
                table: "documentation_runs");

            migrationBuilder.DropIndex(
                name: "UX_index_runs_active_repository",
                schema: "repo",
                table: "index_runs");
        }
    }
}
