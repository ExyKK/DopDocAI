using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Application.Repositories;
using DopDoc.RepositoryService.Domain;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Npgsql;

namespace DopDoc.RepositoryService.Application.Jobs;

public sealed class JobRunApplicationService
{
    public const string DefaultDocumentationTemplate = "developer_handbook";
    private const string UserRequestedTrigger = "user_requested";

    private readonly RepositoryDbContext _db;
    private readonly RepositoryApplicationService _repositories;
    private readonly JobExecutionOptions _options;

    public JobRunApplicationService(
        RepositoryDbContext db,
        RepositoryApplicationService repositories,
        IOptions<JobExecutionOptions> options)
    {
        _db = db;
        _repositories = repositories;
        _options = options.Value;
    }

    public async Task<IndexRunCreateResult> CreateIndexRunAsync(
        Guid userId,
        string? repositoryUrl,
        string? selectedBranch,
        CancellationToken ct)
    {
        var registration = await _repositories.RegisterForIndexAsync(userId, repositoryUrl, selectedBranch, ct);
        var repositoryId = registration.Repository.Id;

        var activeRun = await FindActiveIndexRunAsync(repositoryId, ct);
        if (activeRun is not null)
            return new IndexRunCreateResult(activeRun, Created: false);

        var now = DateTimeOffset.UtcNow;
        var run = new IndexRun
        {
            Id = Guid.NewGuid(),
            RepositoryId = repositoryId,
            RequestedByUserId = userId,
            TriggerKind = UserRequestedTrigger,
            Status = JobRunStatuses.Queued,
            Stage = JobRunStages.Common.Queued,
            ProgressPct = 0,
            ProgressCurrent = 0,
            ProgressTotal = 0,
            Attempt = 0,
            MaxAttempts = _options.MaxAttempts,
            CreatedAt = now,
            UpdatedAt = now
        };

        _db.IndexRuns.Add(run);

        try
        {
            await _db.SaveChangesAsync(ct);
            return new IndexRunCreateResult(run, Created: true);
        }
        catch (DbUpdateException ex) when (IsUniqueViolation(ex))
        {
            _db.ChangeTracker.Clear();
            activeRun = await FindActiveIndexRunAsync(repositoryId, ct)
                ?? throw new InvalidOperationException("Active index run unique constraint was violated, but active run was not found.");

            return new IndexRunCreateResult(activeRun, Created: false);
        }
    }

    public async Task<IndexRun> GetIndexRunAsync(Guid userId, Guid indexRunId, CancellationToken ct)
    {
        var run = await _db.IndexRuns
            .AsNoTracking()
            .Where(x => x.Id == indexRunId)
            .Where(x => _db.UserRepositories.Any(ur =>
                ur.UserId == userId &&
                ur.RepositoryId == x.RepositoryId &&
                ur.Repository.ArchivedAt == null))
            .FirstOrDefaultAsync(ct);

        if (run is null)
            throw IndexRunNotFound(indexRunId);

        return run;
    }

    public async Task<PagedIndexRunResult> ListIndexRunsAsync(
        Guid userId,
        Guid repositoryId,
        RepositoryPagination pagination,
        CancellationToken ct)
    {
        await EnsureRepositoryVisibleAsync(userId, repositoryId, ct);

        var query = _db.IndexRuns
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedIndexRunResult(items, total, pagination.Limit, pagination.Offset);
    }

    public async Task<DocumentationRunCreateResult> CreateDocumentationRunAsync(
        Guid userId,
        Guid repositoryId,
        CreateDocumentationRunCommand command,
        CancellationToken ct)
    {
        var repository = await _db.UserRepositories
            .AsNoTracking()
            .Where(x => x.UserId == userId && x.RepositoryId == repositoryId && x.Repository.ArchivedAt == null)
            .Select(x => x.Repository)
            .FirstOrDefaultAsync(ct);

        if (repository is null)
            throw RepositoryNotFound(repositoryId);

        var readySnapshot = await FindReadySnapshotAsync(repositoryId, command.SnapshotId, ct);
        var snapshot = readySnapshot.Snapshot;

        var templateKind = NormalizeTemplateKind(command.TemplateKind);
        var activeRun = await FindActiveDocumentationRunAsync(repositoryId, snapshot.Id, templateKind, ct);
        if (activeRun is not null)
            return new DocumentationRunCreateResult(activeRun, Created: false);

        var now = DateTimeOffset.UtcNow;

        var run = new DocumentationRun
        {
            Id = Guid.NewGuid(),
            RepositoryId = repositoryId,
            SnapshotId = snapshot.Id,
            SourceIndexRunId = readySnapshot.SourceIndexRunId,
            BaseSnapshotId = command.BaseSnapshotId,
            RequestedByUserId = userId,
            TemplateKind = templateKind,
            Status = JobRunStatuses.Queued,
            Stage = JobRunStages.Common.Queued,
            ProgressPct = 0,
            ProgressCurrent = 0,
            ProgressTotal = 0,
            Attempt = 0,
            MaxAttempts = _options.MaxAttempts,
            CreatedAt = now,
            UpdatedAt = now
        };

        _db.DocumentationRuns.Add(run);

        try
        {
            await _db.SaveChangesAsync(ct);
            return new DocumentationRunCreateResult(run, Created: true);
        }
        catch (DbUpdateException ex) when (IsUniqueViolation(ex))
        {
            _db.ChangeTracker.Clear();
            activeRun = await FindActiveDocumentationRunAsync(repositoryId, snapshot.Id, templateKind, ct)
                ?? throw new InvalidOperationException("Active documentation run unique constraint was violated, but active run was not found.");

            return new DocumentationRunCreateResult(activeRun, Created: false);
        }
    }

    public async Task<DocumentationRun> GetDocumentationRunAsync(Guid userId, Guid documentationRunId, CancellationToken ct)
    {
        var run = await _db.DocumentationRuns
            .AsNoTracking()
            .Where(x => x.Id == documentationRunId)
            .Where(x => _db.UserRepositories.Any(ur =>
                ur.UserId == userId &&
                ur.RepositoryId == x.RepositoryId &&
                ur.Repository.ArchivedAt == null))
            .FirstOrDefaultAsync(ct);

        if (run is null)
            throw DocumentationRunNotFound(documentationRunId);

        return run;
    }

    public async Task<PagedDocumentationRunResult> ListDocumentationRunsAsync(
        Guid userId,
        Guid repositoryId,
        RepositoryPagination pagination,
        CancellationToken ct)
    {
        await EnsureRepositoryVisibleAsync(userId, repositoryId, ct);

        var query = _db.DocumentationRuns
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(x => x.CreatedAt)
            .Skip(pagination.Offset)
            .Take(pagination.Limit)
            .ToListAsync(ct);

        return new PagedDocumentationRunResult(items, total, pagination.Limit, pagination.Offset);
    }

    private async Task EnsureRepositoryVisibleAsync(Guid userId, Guid repositoryId, CancellationToken ct)
    {
        var exists = await _db.UserRepositories
            .AsNoTracking()
            .AnyAsync(x => x.UserId == userId &&
                           x.RepositoryId == repositoryId &&
                           x.Repository.ArchivedAt == null,
                ct);

        if (!exists)
            throw RepositoryNotFound(repositoryId);
    }

    private Task<IndexRun?> FindActiveIndexRunAsync(Guid repositoryId, CancellationToken ct)
    {
        return _db.IndexRuns
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId)
            .Where(x => x.Status == JobRunStatuses.Queued || x.Status == JobRunStatuses.Running)
            .OrderByDescending(x => x.CreatedAt)
            .FirstOrDefaultAsync(ct);
    }

    private Task<DocumentationRun?> FindActiveDocumentationRunAsync(
        Guid repositoryId,
        Guid snapshotId,
        string templateKind,
        CancellationToken ct)
    {
        return _db.DocumentationRuns
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId && x.SnapshotId == snapshotId && x.TemplateKind == templateKind)
            .Where(x => x.Status == JobRunStatuses.Queued || x.Status == JobRunStatuses.Running)
            .OrderByDescending(x => x.CreatedAt)
            .FirstOrDefaultAsync(ct);
    }

    private async Task<ReadySnapshotResult> FindReadySnapshotAsync(
        Guid repositoryId,
        Guid? snapshotId,
        CancellationToken ct)
    {
        if (snapshotId is not null)
        {
            var snapshot = await _db.RepositorySnapshots
                .AsNoTracking()
                .FirstOrDefaultAsync(x => x.RepositoryId == repositoryId && x.Id == snapshotId, ct);

            if (snapshot is null)
                throw SnapshotNotFound(snapshotId.Value);

            var sourceIndexRunId = await FindLatestSucceededIndexRunIdAsync(repositoryId, snapshot.Id, ct);
            if (sourceIndexRunId is null)
                throw SnapshotNotReady(repositoryId, snapshot.Id);

            return new ReadySnapshotResult(snapshot, sourceIndexRunId.Value);
        }

        var ready = await (
                from run in _db.IndexRuns.AsNoTracking()
                join snapshot in _db.RepositorySnapshots.AsNoTracking()
                    on run.SnapshotId equals snapshot.Id
                where run.RepositoryId == repositoryId &&
                      run.SnapshotId != null &&
                      run.Status == JobRunStatuses.Succeeded
                orderby run.FinishedAt ?? run.UpdatedAt descending
                select new ReadySnapshotResult(snapshot, run.Id))
            .FirstOrDefaultAsync(ct);

        if (ready is null)
            throw SnapshotNotReady(repositoryId);

        return ready;
    }

    private async Task<Guid?> FindLatestSucceededIndexRunIdAsync(Guid repositoryId, Guid snapshotId, CancellationToken ct)
    {
        return await _db.IndexRuns
            .AsNoTracking()
            .Where(x => x.RepositoryId == repositoryId &&
                        x.SnapshotId == snapshotId &&
                        x.Status == JobRunStatuses.Succeeded)
            .OrderByDescending(x => x.FinishedAt ?? x.UpdatedAt)
            .Select(x => (Guid?)x.Id)
            .FirstOrDefaultAsync(ct);
    }

    private static string NormalizeTemplateKind(string? templateKind)
    {
        if (string.IsNullOrWhiteSpace(templateKind))
            return DefaultDocumentationTemplate;

        var normalized = templateKind.Trim().ToLowerInvariant();
        if (normalized.Length is < 1 or > 128 ||
            normalized.Any(x => !(char.IsAsciiLetterOrDigit(x) || x == '_' || x == '-')))
        {
            throw new ValidationException(
                "Documentation template kind is invalid",
                errorCode: "documentation_template_kind_invalid");
        }

        return normalized;
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

    private static ConflictException SnapshotNotReady(Guid repositoryId, Guid? snapshotId = null)
    {
        var detail = snapshotId is null
            ? $"Repository {repositoryId} does not have a ready indexed snapshot."
            : $"Repository snapshot {snapshotId} is not ready for documentation generation.";

        return new ConflictException(detail, errorCode: "repository_snapshot_not_ready");
    }

    private static NotFoundException IndexRunNotFound(Guid indexRunId)
    {
        return new NotFoundException(
            $"Index run {indexRunId} was not found.",
            errorCode: "index_run_not_found");
    }

    private static NotFoundException DocumentationRunNotFound(Guid documentationRunId)
    {
        return new NotFoundException(
            $"Documentation run {documentationRunId} was not found.",
            errorCode: "documentation_run_not_found");
    }

    private static bool IsUniqueViolation(DbUpdateException ex)
    {
        return ex.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation };
    }

    private sealed record ReadySnapshotResult(RepositorySnapshot Snapshot, Guid SourceIndexRunId);
}
