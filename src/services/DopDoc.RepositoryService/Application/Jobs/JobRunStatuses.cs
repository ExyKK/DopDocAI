namespace DopDoc.RepositoryService.Application.Jobs;

public static class JobRunStatuses
{
    public const string Queued = "queued";
    public const string Running = "running";
    public const string Succeeded = "succeeded";
    public const string Failed = "failed";
    public const string Canceled = "canceled";
    public const string Stale = "stale";

    public static readonly IReadOnlySet<string> All = new HashSet<string>(StringComparer.Ordinal)
    {
        Queued,
        Running,
        Succeeded,
        Failed,
        Canceled,
        Stale
    };

    public static readonly IReadOnlySet<string> Active = new HashSet<string>(StringComparer.Ordinal)
    {
        Queued,
        Running
    };

    public static readonly IReadOnlySet<string> Terminal = new HashSet<string>(StringComparer.Ordinal)
    {
        Succeeded,
        Failed,
        Canceled,
        Stale
    };

    public static bool IsKnown(string? status)
    {
        return status is not null && All.Contains(status);
    }

    public static bool IsActive(string? status)
    {
        return status is not null && Active.Contains(status);
    }

    public static bool IsTerminal(string? status)
    {
        return status is not null && Terminal.Contains(status);
    }
}
