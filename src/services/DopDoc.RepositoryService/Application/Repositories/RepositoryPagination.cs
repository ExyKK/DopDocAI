using DopDoc.Common.Errors;

namespace DopDoc.RepositoryService.Application.Repositories;

public sealed record RepositoryPagination(int Limit, int Offset)
{
    public const int DefaultLimit = 50;
    public const int MaxLimit = 200;

    public static RepositoryPagination Validate(int? limit, int? offset)
    {
        var normalizedLimit = limit ?? DefaultLimit;
        var normalizedOffset = offset ?? 0;

        if (normalizedLimit is < 1 or > MaxLimit)
        {
            throw new ValidationException(
                $"limit must be between 1 and {MaxLimit}",
                errorCode: "limit_out_of_range",
                extensions: new Dictionary<string, object?> { ["max_limit"] = MaxLimit });
        }

        if (normalizedOffset < 0)
        {
            throw new ValidationException(
                "offset must be greater than or equal to 0",
                errorCode: "offset_out_of_range");
        }

        return new RepositoryPagination(normalizedLimit, normalizedOffset);
    }
}
