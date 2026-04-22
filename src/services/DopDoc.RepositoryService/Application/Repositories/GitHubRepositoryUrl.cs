using System.Text.RegularExpressions;
using DopDoc.Common.Errors;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed record GitHubRepositoryUrl(
    string Provider,
    string Host,
    string Owner,
    string Name,
    string FullName,
    string NormalizedUrl);

public static class GitHubRepositoryUrlParser
{
    private static readonly Regex SshUrlRegex = new(
        @"^git@github\.com:(?<owner>[^/]+)/(?<name>[^/]+?)(?:\.git)?$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly Regex OwnerRegex = new(
        @"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly Regex RepositoryNameRegex = new(
        @"^[a-zA-Z0-9._-]{1,100}$",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    public static GitHubRepositoryUrl Parse(string? rawUrl)
    {
        if (string.IsNullOrWhiteSpace(rawUrl))
            throw new ValidationException("Repository URL is required", errorCode: "repository_url_required");

        var trimmed = rawUrl.Trim();

        if (TryParseSsh(trimmed, out var ssh))
            return ssh;

        if (!trimmed.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
            !trimmed.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            trimmed = $"https://{trimmed}";
        }

        if (!Uri.TryCreate(trimmed, UriKind.Absolute, out var uri))
            throw new ValidationException("Repository URL is invalid", errorCode: "repository_url_invalid");

        if (!string.Equals(uri.Host, "github.com", StringComparison.OrdinalIgnoreCase))
        {
            throw new ValidationException(
                "Only public GitHub repositories are supported",
                errorCode: "repository_provider_unsupported");
        }

        var segments = uri.AbsolutePath
            .Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        if (segments.Length != 2)
        {
            throw new ValidationException(
                "Repository URL must point to a GitHub repository in owner/name format",
                errorCode: "repository_url_invalid");
        }

        return Build(segments[0], segments[1]);
    }

    private static bool TryParseSsh(string rawUrl, out GitHubRepositoryUrl result)
    {
        result = null!;

        var match = SshUrlRegex.Match(rawUrl);
        if (!match.Success)
            return false;

        result = Build(match.Groups["owner"].Value, match.Groups["name"].Value);
        return true;
    }

    private static GitHubRepositoryUrl Build(string owner, string name)
    {
        owner = owner.Trim();
        name = name.Trim();

        if (name.EndsWith(".git", StringComparison.OrdinalIgnoreCase))
            name = name[..^4];

        if (!OwnerRegex.IsMatch(owner) || !RepositoryNameRegex.IsMatch(name))
            throw new ValidationException("Repository owner or name is invalid", errorCode: "repository_url_invalid");

        var normalizedOwner = owner.ToLowerInvariant();
        var normalizedName = name.ToLowerInvariant();
        var fullName = $"{normalizedOwner}/{normalizedName}";

        return new GitHubRepositoryUrl(
            Provider: "github",
            Host: "github.com",
            Owner: normalizedOwner,
            Name: normalizedName,
            FullName: fullName,
            NormalizedUrl: $"https://github.com/{fullName}");
    }
}
