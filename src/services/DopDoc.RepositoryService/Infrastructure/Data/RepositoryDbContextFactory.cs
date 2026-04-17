using DopDoc.Common.Configuration;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Options;

namespace DopDoc.RepositoryService.Infrastructure.Data;

public sealed class RepositoryDbContextFactory : IDesignTimeDbContextFactory<RepositoryDbContext>
{
    public RepositoryDbContext CreateDbContext(string[] args)
    {
        var config = new ConfigurationBuilder()
            .AddJsonFile("appsettings.json", optional: true)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var cs = config.GetConnectionString("RepoDb");
        if (string.IsNullOrWhiteSpace(cs))
            throw new InvalidOperationException("ConnectionStrings:RepoDb is required");

        var schema = config["Db:Schema"] ?? "repo";

        var options = new DbContextOptionsBuilder<RepositoryDbContext>()
            .UseNpgsql(cs, npgsql => npgsql.MigrationsHistoryTable("__EFMigrationsHistory", schema))
            .Options;

        var dbOptions = Options.Create(new DbOptions { Schema = schema });

        return new RepositoryDbContext(options, dbOptions);
    }
}
