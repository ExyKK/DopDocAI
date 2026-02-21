using DopDoc.AuthService.Domain;
using Microsoft.EntityFrameworkCore;

namespace DopDoc.AuthService.Infrastructure.Data;

public sealed class AuthDbContext : DbContext
{
    private readonly string _schema;
    
    public AuthDbContext(DbContextOptions<AuthDbContext> options, IConfiguration config) : base(options)
    {
        _schema = config["Db__Schema"] ?? "auth";
    }
    
    public DbSet<User> Users => Set<User>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();
    
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema(_schema);

        modelBuilder.Entity<User>(builder =>
        {
            builder.ToTable("users");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id)
                .HasDefaultValueSql("gen_random_uuid()");
            
            builder.HasIndex(x => x.Email).IsUnique();
            builder.Property(x => x.Email).IsRequired();
            builder.Property(x => x.PasswordHash).IsRequired();
            
            builder.Property(x => x.IsActive).HasDefaultValue(true);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
        });

        modelBuilder.Entity<RefreshToken>(builder =>
        {
            builder.ToTable("refresh_tokens");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id)
                .HasDefaultValueSql("gen_random_uuid()");
            
            builder.HasIndex(x => x.UserId);
            builder.HasIndex(x => x.TokenHash).IsUnique();
            builder.Property(x => x.TokenHash).IsRequired();
            
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("now()");
            builder.Property(x => x.ExpiresAt).IsRequired();
        });
    }
}