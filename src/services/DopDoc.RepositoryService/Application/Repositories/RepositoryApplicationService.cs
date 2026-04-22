using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed class RepositoryApplicationService
{
    private readonly RepositoryDbContext _db;

    public RepositoryApplicationService(RepositoryDbContext db)
    {
        _db = db;
    }

    public async Task<RepositoryRegistrationResult> RegisterForIndexAsync(
        Guid userId,
        string? repositoryUrl,
        string? selectedBranch,
        CancellationToken ct)
    {
        var parsedUrl = GitHubRepositoryUrlParser.Parse(repositoryUrl);
        var normalizedBranch = RepositoryBranchName.Normalize(selectedBranch);
        var now = DateTimeOffset.UtcNow;

        var repository = await _db.Repositories
            .FirstOrDefaultAsync(x => x.NormalizedUrl == parsedUrl.NormalizedUrl, ct);

        var created = false;

        if (repository is null)
        {
            repository = new RepositoryEntity
            {
                Id = Guid.NewGuid(),
                Provider = parsedUrl.Provider,
                Host = parsedUrl.Host,
                Owner = parsedUrl.Owner,
                Name = parsedUrl.Name,
                FullName = parsedUrl.FullName,
                NormalizedUrl = parsedUrl.NormalizedUrl,
                SelectedBranch = normalizedBranch,
                CreatedByUserId = userId,
                CreatedAt = now,
                UpdatedAt = now
            };

            _db.Repositories.Add(repository);

            try
            {
                await _db.SaveChangesAsync(ct);
                created = true;
            }
            catch (DbUpdateException ex) when (IsUniqueViolation(ex))
            {
                _db.ChangeTracker.Clear();

                repository = await _db.Repositories
                    .FirstOrDefaultAsync(x => x.NormalizedUrl == parsedUrl.NormalizedUrl, ct)
                    ?? throw new InvalidOperationException("Repository unique constraint was violated, but repository row was not found.");
            }
        }
        else
        {
            await UpdateSelectedBranchIfNeededAsync(repository, normalizedBranch, now, ct);
        }

        await EnsureUserRepositoryAsync(userId, repository.Id, now, ct);

        return new RepositoryRegistrationResult(repository, created);
    }

    public async Task<PagedRepositoryResult> ListAsync(Guid userId, RepositoryPagination page, CancellationToken ct)
    {
        var query = _db.UserRepositories
            .AsNoTracking()
            .Where(x => x.UserId == userId && x.Repository.ArchivedAt == null);

        var total = await query.CountAsync(ct);

        var items = await query
            .OrderByDescending(x => x.LastViewedAt ?? x.CreatedAt)
            .ThenByDescending(x => x.Repository.CreatedAt)
            .Skip(page.Offset)
            .Take(page.Limit)
            .Select(x => x.Repository)
            .ToListAsync(ct);

        return new PagedRepositoryResult(items, total, page.Limit, page.Offset);
    }

    public async Task<RepositoryEntity> GetAsync(Guid userId, Guid repositoryId, CancellationToken ct)
    {
        var repository = await _db.UserRepositories
            .AsNoTracking()
            .Where(x => x.UserId == userId && x.RepositoryId == repositoryId && x.Repository.ArchivedAt == null)
            .Select(x => x.Repository)
            .FirstOrDefaultAsync(ct);

        if (repository is null)
        {
            throw new NotFoundException(
                $"Repository {repositoryId} was not found.",
                errorCode: "repository_not_found");
        }

        return repository;
    }

    private async Task UpdateSelectedBranchIfNeededAsync(
        RepositoryEntity repository,
        string? requestedBranch,
        DateTimeOffset now,
        CancellationToken ct)
    {
        if (requestedBranch is null || string.Equals(repository.SelectedBranch, requestedBranch, StringComparison.Ordinal))
            return;

        if (!string.IsNullOrWhiteSpace(repository.SelectedBranch))
        {
            throw new ConflictException(
                "Repository is already configured for a different selected branch",
                errorCode: "repository_branch_conflict",
                extensions: new Dictionary<string, object?>
                {
                    ["selected_branch"] = repository.SelectedBranch,
                    ["requested_branch"] = requestedBranch
                });
        }

        repository.SelectedBranch = requestedBranch;
        repository.UpdatedAt = now;
        await _db.SaveChangesAsync(ct);
    }

    private async Task EnsureUserRepositoryAsync(Guid userId, Guid repositoryId, DateTimeOffset now, CancellationToken ct)
    {
        var link = await _db.UserRepositories.FirstOrDefaultAsync(
            x => x.UserId == userId && x.RepositoryId == repositoryId,
            ct);

        if (link is not null)
        {
            link.LastViewedAt = now;
            await _db.SaveChangesAsync(ct);
            return;
        }

        _db.UserRepositories.Add(new Domain.UserRepository
        {
            UserId = userId,
            RepositoryId = repositoryId,
            CreatedAt = now,
            LastViewedAt = now
        });

        try
        {
            await _db.SaveChangesAsync(ct);
        }
        catch (DbUpdateException ex) when (IsUniqueViolation(ex))
        {
            _db.ChangeTracker.Clear();
        }
    }

    private static bool IsUniqueViolation(DbUpdateException ex)
    {
        return ex.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation };
    }
}
