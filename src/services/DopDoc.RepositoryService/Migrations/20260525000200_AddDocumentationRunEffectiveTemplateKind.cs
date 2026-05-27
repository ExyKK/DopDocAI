using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DopDoc.RepositoryService.Migrations
{
    /// <inheritdoc />
    public partial class AddDocumentationRunEffectiveTemplateKind : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "EffectiveTemplateKind",
                schema: "repo",
                table: "documentation_runs",
                type: "character varying(128)",
                maxLength: 128,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "EffectiveTemplateKind",
                schema: "repo",
                table: "documentation_runs");
        }
    }
}
