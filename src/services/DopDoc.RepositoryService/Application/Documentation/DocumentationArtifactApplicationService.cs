using System.Text.RegularExpressions;
using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Application.Jobs;
using DopDoc.RepositoryService.Domain;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;

namespace DopDoc.RepositoryService.Application.Documentation;

public sealed class DocumentationArtifactApplicationService
{
    private static readonly Regex TokenRegex = new(
        "^[a-z0-9][a-z0-9_-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly Regex Sha256Regex = new(
        "^[a-fA-F0-9]{64}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private readonly RepositoryDbContext _db;

    public DocumentationArtifactApplicationService(RepositoryDbContext db)
    {
        _db = db;
    }

    public async Task<DocumentationArtifact> RegisterAsync(
        Guid documentationRunId,
        RegisterDocumentationArtifactCommand command,
        CancellationToken ct)
    {
        ValidateCommand(command);

        var run = await _db.DocumentationRuns
            .FirstOrDefaultAsync(x => x.Id == documentationRunId, ct);

        if (run is null)
            throw DocumentationRunNotFound(documentationRunId);

        if (run.Status != JobRunStatuses.Running)
        {
            throw new ConflictException(
                "Documentation artifacts can only be registered while the documentation run is running.",
                errorCode: "documentation_run_not_running");
        }

        DocumentationSection? section = null;
        var sectionKey = NormalizeOptionalToken(command.SectionKey, "documentation_section_key_invalid", 128);
        if (sectionKey is not null)
        {
            section = await _db.DocumentationSections
                .FirstOrDefaultAsync(
                    x => x.DocumentationRunId == documentationRunId && x.SectionKey == sectionKey,
                    ct);

            if (section is null)
                throw DocumentationSectionNotFound(documentationRunId, sectionKey);
        }

        var artifactKind = NormalizeToken(command.ArtifactKind, "documentation_artifact_kind_invalid", 128);
        var format = NormalizeToken(command.Format, "documentation_artifact_format_invalid", 64);
        var storageBucket = NormalizeRequired(command.StorageBucket, 128, "documentation_artifact_bucket_required");
        var storageKey = NormalizeRequired(command.StorageKey, null, "documentation_artifact_storage_key_required");
        var contentType = NormalizeRequired(command.ContentType, 256, "documentation_artifact_content_type_required");
        var checksumSha256 = NormalizeSha256(command.ChecksumSha256);

        var artifact = await _db.DocumentationArtifacts
            .FirstOrDefaultAsync(
                x => x.DocumentationRunId == documentationRunId &&
                     x.SectionId == (section == null ? null : section.Id) &&
                     x.ArtifactKind == artifactKind &&
                     x.SchemaVersion == command.SchemaVersion,
                ct);

        if (artifact is null)
        {
            artifact = new DocumentationArtifact
            {
                Id = Guid.NewGuid(),
                DocumentationRunId = documentationRunId,
                SectionId = section?.Id,
                CreatedAt = DateTimeOffset.UtcNow
            };
            _db.DocumentationArtifacts.Add(artifact);
        }

        artifact.ArtifactKind = artifactKind;
        artifact.StorageBucket = storageBucket;
        artifact.StorageKey = storageKey;
        artifact.ContentType = contentType;
        artifact.Format = format;
        artifact.ChecksumSha256 = checksumSha256;
        artifact.SizeBytes = command.SizeBytes;
        artifact.SchemaVersion = command.SchemaVersion;

        if (section is not null)
        {
            section.ArtifactId = artifact.Id;
            section.Status = "generated";
            section.UpdatedAt = DateTimeOffset.UtcNow;
        }

        if (artifactKind == "manifest")
            run.PublishedManifestArtifactId = artifact.Id;

        run.UpdatedAt = DateTimeOffset.UtcNow;

        await _db.SaveChangesAsync(ct);
        return artifact;
    }

    private static void ValidateCommand(RegisterDocumentationArtifactCommand command)
    {
        if (command.SizeBytes < 0)
        {
            throw new ValidationException(
                "size_bytes must be greater than or equal to 0",
                errorCode: "documentation_artifact_size_invalid");
        }

        if (command.SchemaVersion < 1)
        {
            throw new ValidationException(
                "schema_version must be greater than or equal to 1",
                errorCode: "documentation_artifact_schema_version_invalid");
        }
    }

    private static string NormalizeToken(string? value, string errorCode, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("documentation artifact value is required", errorCode: errorCode);

        var normalized = value.Trim().ToLowerInvariant();
        if (normalized.Length > maxLength || !TokenRegex.IsMatch(normalized))
            throw new ValidationException("documentation artifact value is invalid", errorCode: errorCode);

        return normalized;
    }

    private static string? NormalizeOptionalToken(string? value, string errorCode, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        return NormalizeToken(value, errorCode, maxLength);
    }

    private static string NormalizeRequired(string? value, int? maxLength, string errorCode)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("documentation artifact value is required", errorCode: errorCode);

        var normalized = value.Trim();
        if (maxLength is not null && normalized.Length > maxLength.Value)
            throw new ValidationException("documentation artifact value is too long", errorCode: errorCode);

        return normalized;
    }

    private static string NormalizeSha256(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ValidationException(
                "checksum_sha256 is required",
                errorCode: "documentation_artifact_checksum_required");
        }

        var normalized = value.Trim().ToLowerInvariant();
        if (!Sha256Regex.IsMatch(normalized))
        {
            throw new ValidationException(
                "checksum_sha256 must be a 64-character SHA-256 hex string",
                errorCode: "documentation_artifact_checksum_invalid");
        }

        return normalized;
    }

    private static NotFoundException DocumentationRunNotFound(Guid documentationRunId)
    {
        return new NotFoundException(
            $"Documentation run {documentationRunId} was not found.",
            errorCode: "documentation_run_not_found");
    }

    private static NotFoundException DocumentationSectionNotFound(Guid documentationRunId, string sectionKey)
    {
        return new NotFoundException(
            $"Documentation section {sectionKey} was not found for run {documentationRunId}.",
            errorCode: "documentation_section_not_found");
    }
}
