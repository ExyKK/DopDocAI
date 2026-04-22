namespace DopDoc.RepositoryService.Application.Jobs;

public static class JobRunKinds
{
    public const string Index = "index";
    public const string Documentation = "documentation";

    public static readonly IReadOnlySet<string> All = new HashSet<string>(StringComparer.Ordinal)
    {
        Index,
        Documentation
    };
}
