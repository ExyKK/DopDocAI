using Microsoft.EntityFrameworkCore;

namespace DopDoc.ChatService.Infrastructure.Data;

internal static class ChatModelConfiguration
{
    public static void Configure(ModelBuilder modelBuilder, string schema)
    {
        modelBuilder.HasDefaultSchema(schema);

        modelBuilder.Entity<Domain.Chat>(builder =>
        {
            builder.ToTable("chats");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.Title).HasMaxLength(512);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.UpdatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.UserId, x.RepositoryId, x.LastMessageAt });
        });

        modelBuilder.Entity<Domain.ChatMessage>(builder =>
        {
            builder.ToTable("chat_messages");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("gen_random_uuid()");
            builder.Property(x => x.Role).HasMaxLength(32).IsRequired();
            builder.Property(x => x.ContentMarkdown).IsRequired();
            builder.Property(x => x.ModelName).HasMaxLength(256);
            builder.Property(x => x.Provider).HasMaxLength(128);
            builder.Property(x => x.PromptVersion).HasMaxLength(128);
            builder.Property(x => x.FinishReason).HasMaxLength(64);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.HasIndex(x => new { x.ChatId, x.CreatedAt });
            builder.HasOne(x => x.Chat)
                .WithMany(x => x.Messages)
                .HasForeignKey(x => x.ChatId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Domain.ChatMessageSource>(builder =>
        {
            builder.ToTable("chat_message_sources");
            builder.HasKey(x => new { x.MessageId, x.Ordinal });
            builder.Property(x => x.SourceKind).HasMaxLength(64).IsRequired();
            builder.Property(x => x.FilePath).HasMaxLength(2048);
            builder.Property(x => x.SymbolName).HasMaxLength(512);
            builder.Property(x => x.ChunkId).HasMaxLength(256);
            builder.Property(x => x.CitationLabel).HasMaxLength(64);
            builder.HasOne(x => x.Message)
                .WithMany(x => x.Sources)
                .HasForeignKey(x => x.MessageId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
