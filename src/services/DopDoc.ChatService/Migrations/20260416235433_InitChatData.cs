using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DopDoc.ChatService.Migrations
{
    /// <inheritdoc />
    public partial class InitChatData : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql(@"CREATE SCHEMA IF NOT EXISTS chat;");
            migrationBuilder.Sql(@"CREATE EXTENSION IF NOT EXISTS pgcrypto;");
            
            migrationBuilder.EnsureSchema(
                name: "chat");

            migrationBuilder.CreateTable(
                name: "chats",
                schema: "chat",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    RepositoryId = table.Column<Guid>(type: "uuid", nullable: false),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Title = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    LastMessageAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ArchivedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_chats", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "chat_messages",
                schema: "chat",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    ChatId = table.Column<Guid>(type: "uuid", nullable: false),
                    Role = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    ContentMarkdown = table.Column<string>(type: "text", nullable: false),
                    ModelName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    Provider = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    PromptVersion = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    InputTokens = table.Column<int>(type: "integer", nullable: true),
                    OutputTokens = table.Column<int>(type: "integer", nullable: true),
                    FinishReason = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    RetrievalTimeMs = table.Column<int>(type: "integer", nullable: true),
                    GenerationTimeMs = table.Column<int>(type: "integer", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_chat_messages", x => x.Id);
                    table.ForeignKey(
                        name: "FK_chat_messages_chats_ChatId",
                        column: x => x.ChatId,
                        principalSchema: "chat",
                        principalTable: "chats",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "chat_message_sources",
                schema: "chat",
                columns: table => new
                {
                    MessageId = table.Column<Guid>(type: "uuid", nullable: false),
                    Ordinal = table.Column<int>(type: "integer", nullable: false),
                    SnapshotId = table.Column<Guid>(type: "uuid", nullable: false),
                    SourceKind = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    FilePath = table.Column<string>(type: "character varying(2048)", maxLength: 2048, nullable: true),
                    SymbolName = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: true),
                    StartLine = table.Column<int>(type: "integer", nullable: true),
                    EndLine = table.Column<int>(type: "integer", nullable: true),
                    ChunkId = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    Score = table.Column<double>(type: "double precision", nullable: true),
                    UsedInAnswer = table.Column<bool>(type: "boolean", nullable: false),
                    CitationLabel = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_chat_message_sources", x => new { x.MessageId, x.Ordinal });
                    table.ForeignKey(
                        name: "FK_chat_message_sources_chat_messages_MessageId",
                        column: x => x.MessageId,
                        principalSchema: "chat",
                        principalTable: "chat_messages",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_chat_messages_ChatId_CreatedAt",
                schema: "chat",
                table: "chat_messages",
                columns: new[] { "ChatId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_chats_UserId_RepositoryId_LastMessageAt",
                schema: "chat",
                table: "chats",
                columns: new[] { "UserId", "RepositoryId", "LastMessageAt" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "chat_message_sources",
                schema: "chat");

            migrationBuilder.DropTable(
                name: "chat_messages",
                schema: "chat");

            migrationBuilder.DropTable(
                name: "chats",
                schema: "chat");
        }
    }
}
