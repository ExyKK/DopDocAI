using DopDoc.Common.Configuration;
using DopDoc.RepositoryService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DopDoc.RepositoryService.Infrastructure.Data;

public sealed class RepositoryDbContext : DbContext
{
    private readonly string _schema;
    public string Schema => _schema;

    public RepositoryDbContext(DbContextOptions<RepositoryDbContext> options, IOptions<DbOptions> dbOptions)
        : base(options)
    {
        _schema = dbOptions.Value.Schema;
    }

    public DbSet<Repository> Repositories => Set<Repository>();
    public DbSet<UserRepository> UserRepositories => Set<UserRepository>();
    public DbSet<RepositorySnapshot> RepositorySnapshots => Set<RepositorySnapshot>();
    public DbSet<IndexRun> IndexRuns => Set<IndexRun>();
    public DbSet<IndexRunEvent> IndexRunEvents => Set<IndexRunEvent>();
    public DbSet<AnalysisArtifact> AnalysisArtifacts => Set<AnalysisArtifact>();
    public DbSet<DocumentationRun> DocumentationRuns => Set<DocumentationRun>();
    public DbSet<DocumentationSection> DocumentationSections => Set<DocumentationSection>();
    public DbSet<DocumentationSectionSource> DocumentationSectionSources => Set<DocumentationSectionSource>();
    public DbSet<DocumentationArtifact> DocumentationArtifacts => Set<DocumentationArtifact>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        RepositoryModelConfiguration.Configure(modelBuilder, _schema);
    }
}
