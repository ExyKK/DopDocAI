using System.Text.RegularExpressions;
using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Domain;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed class AnalysisArtifactApplicationService
{
    private static readonly Regex ArtifactTokenRegex = new(
        "^[a-z0-9][a-z0-9_-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly Regex Sha256Regex = new(
        "^[a-fA-F0-9]{64}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private readonly RepositoryDbContext _db;

    public AnalysisArtifactApplicationService(RepositoryDbContext db)
    {
        _db = db;
    }

    public async Task<AnalysisArtifactUpsertResult> UpsertAsync(
        Guid repositoryId,
        Guid snapshotId,
        UpsertAnalysisArtifactCommand command,
        CancellationToken ct)
    {
        ValidateCommand(command);

        var snapshot = await _db.RepositorySnapshots.FirstOrDefaultAsync(
            x => x.RepositoryId == repositoryId && x.Id == snapshotId,
            ct);

        if (snapshot is null)
            throw SnapshotNotFound(snapshotId);

        var indexRun = await _db.IndexRuns.FirstOrDefaultAsync(x => x.Id == command.ProducedByIndexRunId, ct);
        if (indexRun is null)
            throw IndexRunNotFound(command.ProducedByIndexRunId);

        if (indexRun.RepositoryId != repositoryId)
        {
            throw new ConflictException(
                "Index run belongs to a different repository",
                errorCode: "analysis_artifact_repository_conflict");
        }

        if (indexRun.SnapshotId != snapshotId)
        {
            throw new ConflictException(
                "Index run is not attached to the requested snapshot",
                errorCode: "analysis_artifact_snapshot_conflict");
        }

        var artifactKind = NormalizeArtifactToken(command.ArtifactKind, "analysis_artifact_kind_invalid", 128);
        var format = NormalizeArtifactToken(command.Format, "analysis_artifact_format_invalid", 64);
        var storageBucket = NormalizeRequired(command.StorageBucket, 128, "analysis_artifact_bucket_required");
        var storageKey = NormalizeRequired(command.StorageKey, null, "analysis_artifact_storage_key_required");
        var contentType = NormalizeRequired(command.ContentType, 256, "analysis_artifact_content_type_required");
        var checksumSha256 = NormalizeSha256(command.ChecksumSha256);
        var now = DateTimeOffset.UtcNow;

        var artifact = await _db.AnalysisArtifacts.FirstOrDefaultAsync(
            x => x.SnapshotId == snapshotId && x.ArtifactKind == artifactKind && x.SchemaVersion == command.SchemaVersion,
            ct);

        var created = false;
        if (artifact is null)
        {
            artifact = new AnalysisArtifact
            {
                Id = Guid.NewGuid(),
                SnapshotId = snapshotId,
                CreatedAt = now
            };

            _db.AnalysisArtifacts.Add(artifact);
            created = true;
        }

        ApplyArtifactMetadata(
            artifact,
            command,
            artifactKind,
            storageBucket,
            storageKey,
            contentType,
            format,
            checksumSha256);

        try
        {
            await _db.SaveChangesAsync(ct);
        }
        catch (DbUpdateException ex) when (created && IsUniqueViolation(ex))
        {
            _db.ChangeTracker.Clear();

            artifact = await _db.AnalysisArtifacts.FirstOrDefaultAsync(
                x => x.SnapshotId == snapshotId && x.ArtifactKind == artifactKind && x.SchemaVersion == command.SchemaVersion,
                ct) ?? throw new InvalidOperationException("Analysis artifact unique constraint was violated, but artifact row was not found.");

            ApplyArtifactMetadata(
                artifact,
                command,
                artifactKind,
                storageBucket,
                storageKey,
                contentType,
                format,
                checksumSha256);

            await _db.SaveChangesAsync(ct);
            created = false;
        }

        return new AnalysisArtifactUpsertResult(artifact, created);
    }

    private static void ValidateCommand(UpsertAnalysisArtifactCommand command)
    {
        if (command.ProducedByIndexRunId == Guid.Empty)
        {
            throw new ValidationException(
                "produced_by_index_run_id is required",
                errorCode: "analysis_artifact_index_run_required");
        }

        if (command.SizeBytes < 0)
        {
            throw new ValidationException(
                "size_bytes must be greater than or equal to 0",
                errorCode: "analysis_artifact_size_invalid");
        }

        if (command.RowCount is < 0)
        {
            throw new ValidationException(
                "row_count must be greater than or equal to 0",
                errorCode: "analysis_artifact_row_count_invalid");
        }

        if (command.SchemaVersion < 1)
        {
            throw new ValidationException(
                "schema_version must be greater than or equal to 1",
                errorCode: "analysis_artifact_schema_version_invalid");
        }
    }

    private static void ApplyArtifactMetadata(
        AnalysisArtifact artifact,
        UpsertAnalysisArtifactCommand command,
        string artifactKind,
        string storageBucket,
        string storageKey,
        string contentType,
        string format,
        string checksumSha256)
    {
        artifact.ProducedByIndexRunId = command.ProducedByIndexRunId;
        artifact.ArtifactKind = artifactKind;
        artifact.StorageBucket = storageBucket;
        artifact.StorageKey = storageKey;
        artifact.ContentType = contentType;
        artifact.Format = format;
        artifact.ChecksumSha256 = checksumSha256;
        artifact.SizeBytes = command.SizeBytes;
        artifact.RowCount = command.RowCount;
        artifact.SchemaVersion = command.SchemaVersion;
    }

    private static string NormalizeArtifactToken(string? value, string errorCode, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("Artifact value is required", errorCode: errorCode);

        var normalized = value.Trim().ToLowerInvariant();
        if (normalized.Length > maxLength || !ArtifactTokenRegex.IsMatch(normalized))
            throw new ValidationException("Artifact value is invalid", errorCode: errorCode);

        return normalized;
    }

    private static string NormalizeRequired(string? value, int? maxLength, string errorCode)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("Artifact value is required", errorCode: errorCode);

        var normalized = value.Trim();
        if (maxLength is not null && normalized.Length > maxLength.Value)
            throw new ValidationException("Artifact value is too long", errorCode: errorCode);

        return normalized;
    }

    private static string NormalizeSha256(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ValidationException(
                "checksum_sha256 is required",
                errorCode: "analysis_artifact_checksum_required");
        }

        var normalized = value.Trim().ToLowerInvariant();
        if (!Sha256Regex.IsMatch(normalized))
        {
            throw new ValidationException(
                "checksum_sha256 must be a 64-character SHA-256 hex string",
                errorCode: "analysis_artifact_checksum_invalid");
        }

        return normalized;
    }

    private static NotFoundException SnapshotNotFound(Guid snapshotId)
    {
        return new NotFoundException(
            $"Repository snapshot {snapshotId} was not found.",
            errorCode: "repository_snapshot_not_found");
    }

    private static NotFoundException IndexRunNotFound(Guid indexRunId)
    {
        return new NotFoundException(
            $"Index run {indexRunId} was not found.",
            errorCode: "index_run_not_found");
    }

    private static bool IsUniqueViolation(DbUpdateException ex)
    {
        return ex.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation };
    }
}
