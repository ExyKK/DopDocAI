using DopDoc.Common.Errors;

namespace DopDoc.RepositoryService.Application.Repositories;

public static class RepositoryBranchName
{
    public static string? Normalize(string? selectedBranch)
    {
        if (string.IsNullOrWhiteSpace(selectedBranch))
            return null;

        var branch = selectedBranch.Trim();
        const string headsPrefix = "refs/heads/";
        if (branch.StartsWith(headsPrefix, StringComparison.Ordinal))
            branch = branch[headsPrefix.Length..];

        if (branch.Length is < 1 or > 256)
        {
            throw new ValidationException(
                "Selected branch length must be between 1 and 256 characters",
                errorCode: "selected_branch_invalid");
        }

        if (branch.Any(char.IsControl) || branch.Contains(' '))
            throw new ValidationException("Selected branch is invalid", errorCode: "selected_branch_invalid");

        return branch;
    }
}
