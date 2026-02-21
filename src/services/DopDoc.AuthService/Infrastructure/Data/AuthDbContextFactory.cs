using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace DopDoc.AuthService.Infrastructure.Data;

public sealed class AuthDbContextFactory : IDesignTimeDbContextFactory<AuthDbContext>
{
    public AuthDbContext CreateDbContext(string[] args)
    {
        var config = new ConfigurationBuilder()
            .AddJsonFile("appsettings.json", optional: true)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var cs = config.GetConnectionString("AuthDb") ?? config["ConnectionStrings__AuthDb"];
        if (string.IsNullOrWhiteSpace(cs))
            throw new InvalidOperationException("ConnectionStrings:AuthDb is required");

        var schema = config["Db__Schema"] ?? "auth";

        var options = new DbContextOptionsBuilder<AuthDbContext>()
            .UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", schema))
            .Options;
        
        return new AuthDbContext(options, config);
    }
}