using DopDoc.Common.Configuration;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Infrastructure.Data;

public sealed class ChatDbContextFactory : IDesignTimeDbContextFactory<ChatDbContext>
{
    public ChatDbContext CreateDbContext(string[] args)
    {
        var config = new ConfigurationBuilder()
            .AddJsonFile("appsettings.json", optional: true)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var cs = config.GetConnectionString("ChatDb");
        if (string.IsNullOrWhiteSpace(cs))
            throw new InvalidOperationException("ConnectionStrings:ChatDb is required");

        var schema = config["Db:Schema"] ?? "chat";

        var options = new DbContextOptionsBuilder<ChatDbContext>()
            .UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", schema))
            .Options;

        var dbOptions = Options.Create(new DbOptions { Schema = schema });

        return new ChatDbContext(options, dbOptions);
    }
}
