using System.Text.RegularExpressions;
using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;
using RepositorySnapshotEntity = DopDoc.RepositoryService.Domain.RepositorySnapshot;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed class RepositorySnapshotApplicationService
{
    private static readonly Regex GitObjectHashRegex = new(
        "^[a-fA-F0-9]{40,64}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private readonly RepositoryDbContext _db;

    public RepositorySnapshotApplicationService(RepositoryDbContext db)
    {
        _db = db;
    }

    public async Task<PagedRepositorySnapshotResult> ListAsync(
        Guid userId,
        Guid repositoryId,
        RepositoryPagination page,
        CancellationToken ct)
    {
        await EnsureUserCanAccessRepositoryAsync(userId, repositoryId, ct);

        var query = _db.RepositorySnapshots
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId);

        var total = await query.CountAsync(ct);

        var items = await query
            .OrderByDescending(x => x.CommitCommittedAt ?? x.CommitAuthoredAt ?? x.CreatedAt)
            .ThenByDescending(x => x.CreatedAt)
            .Skip(page.Offset)
            .Take(page.Limit)
            .ToListAsync(ct);

        return new PagedRepositorySnapshotResult(items, total, page.Limit, page.Offset);
    }

    public async Task<RepositorySnapshotEntity> GetAsync(
        Guid userId,
        Guid repositoryId,
        Guid snapshotId,
        CancellationToken ct)
    {
        await EnsureUserCanAccessRepositoryAsync(userId, repositoryId, ct);

        var snapshot = await _db.RepositorySnapshots
            .AsNoTracking()
            .FirstOrDefaultAsync(x => x.RepositoryId == repositoryId && x.Id == snapshotId, ct);

        if (snapshot is null)
            throw SnapshotNotFound(snapshotId);

        return snapshot;
    }

    public async Task<RepositorySnapshotUpsertResult> UpsertAsync(
        Guid repositoryId,
        UpsertRepositorySnapshotCommand command,
        CancellationToken ct)
    {
        ValidateSnapshotCommand(command);

        var repository = await _db.Repositories.FirstOrDefaultAsync(x => x.Id == repositoryId, ct);
        if (repository is null || repository.ArchivedAt is not null)
            throw RepositoryNotFound(repositoryId);

        var commitSha = NormalizeGitHash(command.CommitSha);
        var treeHash = NormalizeGitHash(command.TreeHash);
        var branchName = RepositoryBranchName.Require(command.BranchName, "branch_name_required");
        var now = DateTimeOffset.UtcNow;

        var snapshot = await _db.RepositorySnapshots.FirstOrDefaultAsync(
            x => x.RepositoryId == repositoryId && x.CommitSha == commitSha,
            ct);

        var created = false;

        if (snapshot is null)
        {
            snapshot = new RepositorySnapshotEntity
            {
                Id = Guid.NewGuid(),
                RepositoryId = repositoryId,
                CreatedAt = now
            };

            _db.RepositorySnapshots.Add(snapshot);
            created = true;
        }

        ApplySnapshotMetadata(snapshot, command, branchName, commitSha, treeHash);
        UpdateRepositoryBranches(repository, branchName, command.SetActive, snapshot.Id, now);

        try
        {
            await _db.SaveChangesAsync(ct);
        }
        catch (DbUpdateException ex) when (created && IsUniqueViolation(ex))
        {
            _db.ChangeTracker.Clear();

            snapshot = await _db.RepositorySnapshots.FirstOrDefaultAsync(
                x => x.RepositoryId == repositoryId && x.CommitSha == commitSha,
                ct) ?? throw new InvalidOperationException("Snapshot unique constraint was violated, but snapshot row was not found.");

            repository = await _db.Repositories.FirstAsync(x => x.Id == repositoryId, ct);
            ApplySnapshotMetadata(snapshot, command, branchName, commitSha, treeHash);
            UpdateRepositoryBranches(repository, branchName, command.SetActive, snapshot.Id, now);
            await _db.SaveChangesAsync(ct);

            created = false;
        }

        return new RepositorySnapshotUpsertResult(snapshot, created);
    }

    public async Task<RepositorySnapshotEntity> GetByCommitAsync(Guid repositoryId, string commitSha, CancellationToken ct)
    {
        var normalizedCommitSha = NormalizeGitHash(commitSha);

        var snapshot = await _db.RepositorySnapshots
            .AsNoTracking()
            .FirstOrDefaultAsync(x => x.RepositoryId == repositoryId && x.CommitSha == normalizedCommitSha, ct);

        if (snapshot is null)
        {
            throw new NotFoundException(
                $"Snapshot for commit {normalizedCommitSha} was not found.",
                errorCode: "repository_snapshot_not_found");
        }

        return snapshot;
    }

    public async Task<RepositorySnapshotEntity> ActivateAsync(Guid repositoryId, Guid snapshotId, CancellationToken ct)
    {
        var repository = await _db.Repositories.FirstOrDefaultAsync(x => x.Id == repositoryId, ct);
        if (repository is null || repository.ArchivedAt is not null)
            throw RepositoryNotFound(repositoryId);

        var snapshot = await _db.RepositorySnapshots.FirstOrDefaultAsync(
            x => x.RepositoryId == repositoryId && x.Id == snapshotId,
            ct);

        if (snapshot is null)
            throw SnapshotNotFound(snapshotId);

        repository.ActiveSnapshotId = snapshot.Id;
        repository.DefaultBranch ??= snapshot.BranchName;
        repository.SelectedBranch ??= snapshot.BranchName;
        repository.UpdatedAt = DateTimeOffset.UtcNow;

        await _db.SaveChangesAsync(ct);
        return snapshot;
    }

    private async Task EnsureUserCanAccessRepositoryAsync(Guid userId, Guid repositoryId, CancellationToken ct)
    {
        var exists = await _db.UserRepositories
            .AsNoTracking()
            .AnyAsync(x => x.UserId == userId && x.RepositoryId == repositoryId && x.Repository.ArchivedAt == null, ct);

        if (!exists)
            throw RepositoryNotFound(repositoryId);
    }

    private static void ValidateSnapshotCommand(UpsertRepositorySnapshotCommand command)
    {
        if (string.IsNullOrWhiteSpace(command.CommitSha))
            throw new ValidationException("commit_sha is required", errorCode: "commit_sha_required");

        if (string.IsNullOrWhiteSpace(command.TreeHash))
            throw new ValidationException("tree_hash is required", errorCode: "tree_hash_required");

        if (command.FilesTotal < 0 || command.GoFilesTotal < 0 || command.ReadmeFilesTotal < 0 || command.BytesTotal < 0)
        {
            throw new ValidationException(
                "Snapshot counters must be greater than or equal to 0",
                errorCode: "snapshot_counters_invalid");
        }

        if (command.GoFilesTotal > command.FilesTotal || command.ReadmeFilesTotal > command.FilesTotal)
        {
            throw new ValidationException(
                "Language and README counters cannot exceed files_total",
                errorCode: "snapshot_counters_invalid");
        }
    }

    private static void ApplySnapshotMetadata(
        RepositorySnapshotEntity snapshot,
        UpsertRepositorySnapshotCommand command,
        string branchName,
        string commitSha,
        string treeHash)
    {
        snapshot.BranchName = branchName;
        snapshot.CommitSha = commitSha;
        snapshot.TreeHash = treeHash;
        snapshot.CommitSubject = NormalizeNullable(command.CommitSubject);
        snapshot.CommitMessage = NormalizeNullable(command.CommitMessage);
        snapshot.CommitAuthorName = NormalizeNullable(command.CommitAuthorName);
        snapshot.CommitAuthorEmail = NormalizeNullable(command.CommitAuthorEmail);
        snapshot.CommitAuthoredAt = command.CommitAuthoredAt;
        snapshot.CommitCommittedAt = command.CommitCommittedAt;
        snapshot.FilesTotal = command.FilesTotal;
        snapshot.GoFilesTotal = command.GoFilesTotal;
        snapshot.ReadmeFilesTotal = command.ReadmeFilesTotal;
        snapshot.BytesTotal = command.BytesTotal;
    }

    private static void UpdateRepositoryBranches(
        RepositoryEntity repository,
        string branchName,
        bool setActive,
        Guid snapshotId,
        DateTimeOffset now)
    {
        if (!string.IsNullOrWhiteSpace(repository.SelectedBranch) &&
            !string.Equals(repository.SelectedBranch, branchName, StringComparison.Ordinal))
        {
            throw new ConflictException(
                "Repository is already configured for a different selected branch",
                errorCode: "repository_branch_conflict",
                extensions: new Dictionary<string, object?>
                {
                    ["selected_branch"] = repository.SelectedBranch,
                    ["snapshot_branch"] = branchName
                });
        }

        repository.DefaultBranch ??= branchName;
        repository.SelectedBranch ??= branchName;

        if (setActive)
            repository.ActiveSnapshotId = snapshotId;

        repository.UpdatedAt = now;
    }

    private static string NormalizeGitHash(string value)
    {
        var normalized = value.Trim().ToLowerInvariant();
        if (!GitObjectHashRegex.IsMatch(normalized))
            throw new ValidationException("Git object hash is invalid", errorCode: "git_hash_invalid");

        return normalized;
    }

    private static string? NormalizeNullable(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static NotFoundException RepositoryNotFound(Guid repositoryId)
    {
        return new NotFoundException(
            $"Repository {repositoryId} was not found.",
            errorCode: "repository_not_found");
    }

    private static NotFoundException SnapshotNotFound(Guid snapshotId)
    {
        return new NotFoundException(
            $"Repository snapshot {snapshotId} was not found.",
            errorCode: "repository_snapshot_not_found");
    }

    private static bool IsUniqueViolation(DbUpdateException ex)
    {
        return ex.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation };
    }
}
