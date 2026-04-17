using DopDoc.ChatService.Domain;
using DopDoc.Common.Configuration;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Infrastructure.Data;

public sealed class ChatDbContext : DbContext
{
    private readonly string _schema;
    public string Schema => _schema;

    public ChatDbContext(DbContextOptions<ChatDbContext> options, IOptions<DbOptions> dbOptions)
        : base(options)
    {
        _schema = dbOptions.Value.Schema;
    }

    public DbSet<Chat> Chats => Set<Chat>();
    public DbSet<ChatMessage> ChatMessages => Set<ChatMessage>();
    public DbSet<ChatMessageSource> ChatMessageSources => Set<ChatMessageSource>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ChatModelConfiguration.Configure(modelBuilder, _schema);
    }
}
