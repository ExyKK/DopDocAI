using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DopDoc.RepositoryService.Migrations
{
    /// <inheritdoc />
    public partial class AddDocumentationArtifactAttempt : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "Attempt",
                schema: "repo",
                table: "documentation_artifacts",
                type: "integer",
                nullable: false,
                defaultValue: 1);

            migrationBuilder.DropIndex(
                name: "IX_documentation_artifacts_DocumentationRunId_ArtifactKind",
                schema: "repo",
                table: "documentation_artifacts");

            migrationBuilder.CreateIndex(
                name: "IX_documentation_artifacts_DocumentationRunId_Attempt_ArtifactKind",
                schema: "repo",
                table: "documentation_artifacts",
                columns: new[] { "DocumentationRunId", "Attempt", "ArtifactKind" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_documentation_artifacts_DocumentationRunId_Attempt_ArtifactKind",
                schema: "repo",
                table: "documentation_artifacts");

            migrationBuilder.CreateIndex(
                name: "IX_documentation_artifacts_DocumentationRunId_ArtifactKind",
                schema: "repo",
                table: "documentation_artifacts",
                columns: new[] { "DocumentationRunId", "ArtifactKind" });

            migrationBuilder.DropColumn(
                name: "Attempt",
                schema: "repo",
                table: "documentation_artifacts");
        }
    }
}
