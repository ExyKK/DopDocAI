using System.Text.RegularExpressions;
using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Application.Jobs;
using DopDoc.RepositoryService.Domain;
using DopDoc.RepositoryService.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;

namespace DopDoc.RepositoryService.Application.Documentation;

public sealed class DocumentationSectionApplicationService
{
    private static readonly Regex TokenRegex = new(
        "^[a-z0-9][a-z0-9_-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly IReadOnlySet<string> AllowedSectionStatuses = new HashSet<string>(StringComparer.Ordinal)
    {
        "planned",
        "evidence_ready",
        "generated",
        "verified",
        "failed"
    };

    private readonly RepositoryDbContext _db;

    public DocumentationSectionApplicationService(RepositoryDbContext db)
    {
        _db = db;
    }

    public async Task<IReadOnlyList<DocumentationSection>> ReplacePlanAsync(
        Guid documentationRunId,
        ReplaceDocumentationSectionsCommand command,
        CancellationToken ct)
    {
        var run = await _db.DocumentationRuns
            .FirstOrDefaultAsync(x => x.Id == documentationRunId, ct);

        if (run is null)
            throw DocumentationRunNotFound(documentationRunId);

        if (run.Status != JobRunStatuses.Running)
        {
            throw new ConflictException(
                "Documentation sections can only be replaced while the documentation run is running.",
                errorCode: "documentation_run_not_running");
        }

        ValidateCommand(command, run.SnapshotId);

        var existing = await _db.DocumentationSections
            .Where(x => x.DocumentationRunId == documentationRunId)
            .ToListAsync(ct);

        if (existing.Count > 0)
        {
            _db.DocumentationSections.RemoveRange(existing);
            await _db.SaveChangesAsync(ct);
        }

        var now = DateTimeOffset.UtcNow;
        foreach (var sectionCommand in command.Sections.OrderBy(x => x.Ordinal))
        {
            var sources = sectionCommand.Sources
                .OrderBy(x => x.Ordinal)
                .Select(source => new DocumentationSectionSource
                {
                    Ordinal = source.Ordinal,
                    SnapshotId = source.SnapshotId,
                    SourceKind = NormalizeToken(source.SourceKind, "documentation_section_source_kind_invalid", 64),
                    FilePath = NormalizeOptional(source.FilePath, 2048),
                    SymbolName = NormalizeOptional(source.SymbolName, 512),
                    StartLine = source.StartLine,
                    EndLine = source.EndLine,
                    ChunkId = NormalizeOptional(source.ChunkId, 256),
                    Score = source.Score,
                    Note = NormalizeOptional(source.Note, 1024)
                })
                .ToList();

            _db.DocumentationSections.Add(new DocumentationSection
            {
                Id = Guid.NewGuid(),
                DocumentationRunId = documentationRunId,
                SectionKey = NormalizeToken(sectionCommand.SectionKey, "documentation_section_key_invalid", 128),
                Title = NormalizeRequired(sectionCommand.Title, 256, "documentation_section_title_required"),
                Ordinal = sectionCommand.Ordinal,
                Status = NormalizeSectionStatus(sectionCommand.Status),
                SourceCount = sources.Count,
                UnsupportedClaims = 0,
                CreatedAt = now,
                UpdatedAt = now,
                Sources = sources
            });
        }

        await _db.SaveChangesAsync(ct);

        return await _db.DocumentationSections
            .AsNoTracking()
            .Include(x => x.Sources.OrderBy(s => s.Ordinal))
            .Where(x => x.DocumentationRunId == documentationRunId)
            .OrderBy(x => x.Ordinal)
            .ToListAsync(ct);
    }

    private static void ValidateCommand(ReplaceDocumentationSectionsCommand command, Guid expectedSnapshotId)
    {
        if (command.Sections.Count == 0)
        {
            throw new ValidationException(
                "documentation section plan must contain at least one section",
                errorCode: "documentation_section_plan_empty");
        }

        if (command.Sections.Count > 100)
        {
            throw new ValidationException(
                "documentation section plan contains too many sections",
                errorCode: "documentation_section_plan_too_large");
        }

        var keys = new HashSet<string>(StringComparer.Ordinal);
        var ordinals = new HashSet<int>();
        foreach (var section in command.Sections)
        {
            var key = NormalizeToken(section.SectionKey, "documentation_section_key_invalid", 128);
            if (!keys.Add(key))
            {
                throw new ValidationException(
                    $"duplicate documentation section key: {key}",
                    errorCode: "documentation_section_key_duplicate");
            }

            if (section.Ordinal < 1 || !ordinals.Add(section.Ordinal))
            {
                throw new ValidationException(
                    "documentation section ordinal is invalid or duplicated",
                    errorCode: "documentation_section_ordinal_invalid");
            }

            NormalizeRequired(section.Title, 256, "documentation_section_title_required");
            NormalizeSectionStatus(section.Status);
            ValidateSources(section.Sources, expectedSnapshotId);
        }
    }

    private static void ValidateSources(
        IReadOnlyList<DocumentationSectionSourceCommand> sources,
        Guid expectedSnapshotId)
    {
        if (sources.Count > 200)
        {
            throw new ValidationException(
                "documentation section contains too many sources",
                errorCode: "documentation_section_sources_too_large");
        }

        var ordinals = new HashSet<int>();
        foreach (var source in sources)
        {
            if (source.Ordinal < 1 || !ordinals.Add(source.Ordinal))
            {
                throw new ValidationException(
                    "documentation section source ordinal is invalid or duplicated",
                    errorCode: "documentation_section_source_ordinal_invalid");
            }

            if (source.SnapshotId != expectedSnapshotId)
            {
                throw new ValidationException(
                    "documentation section source snapshot does not match the run snapshot",
                    errorCode: "documentation_section_source_snapshot_invalid");
            }

            NormalizeToken(source.SourceKind, "documentation_section_source_kind_invalid", 64);
            NormalizeOptional(source.FilePath, 2048);
            NormalizeOptional(source.SymbolName, 512);
            NormalizeOptional(source.ChunkId, 256);
            NormalizeOptional(source.Note, 1024);

            if ((source.StartLine is null) != (source.EndLine is null) ||
                source.StartLine is < 1 ||
                source.EndLine is < 1 ||
                (source.StartLine.HasValue &&
                 source.EndLine.HasValue &&
                 source.EndLine.Value < source.StartLine.Value))
            {
                throw new ValidationException(
                    "documentation section source line range is invalid",
                    errorCode: "documentation_section_source_lines_invalid");
            }
        }
    }

    private static string NormalizeSectionStatus(string? value)
    {
        var normalized = NormalizeToken(value, "documentation_section_status_invalid", 64);
        if (!AllowedSectionStatuses.Contains(normalized))
        {
            throw new ValidationException(
                "documentation section status is invalid",
                errorCode: "documentation_section_status_invalid");
        }

        return normalized;
    }

    private static string NormalizeToken(string? value, string errorCode, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("documentation section value is required", errorCode: errorCode);

        var normalized = value.Trim().ToLowerInvariant();
        if (normalized.Length > maxLength || !TokenRegex.IsMatch(normalized))
            throw new ValidationException("documentation section value is invalid", errorCode: errorCode);

        return normalized;
    }

    private static string NormalizeRequired(string? value, int maxLength, string errorCode)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ValidationException("documentation section value is required", errorCode: errorCode);

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ValidationException("documentation section value is too long", errorCode: errorCode);

        return normalized;
    }

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            return normalized[..maxLength];

        return normalized;
    }

    private static NotFoundException DocumentationRunNotFound(Guid documentationRunId)
    {
        return new NotFoundException(
            $"Documentation run {documentationRunId} was not found.",
            errorCode: "documentation_run_not_found");
    }
}
