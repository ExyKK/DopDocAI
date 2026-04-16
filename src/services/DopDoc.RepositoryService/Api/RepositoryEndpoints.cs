using DopDoc.Common.Errors;
using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Api.Contracts;

namespace DopDoc.RepositoryService.Api;

public static class RepositoryEndpoints
{
    public static RouteGroupBuilder MapRepositoryEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1/repos").WithTags("repos");

        g.MapGet("", (int limit, int offset, IUserContextAccessor userContext) =>
        {
            ValidatePagination(limit, offset);
            _ = userContext.GetRequiredUserId();

            var response = new PagedResponse<RepositoryListItemResponse>(
                Items: [],
                Limit: limit,
                Offset: offset,
                HasMore: false,
                TotalCount: 0);

            return TypedResults.Ok(response);
        })
        .WithName("ListRepositories");

        return g;
    }

    private static void ValidatePagination(int limit, int offset)
    {
        if (limit is < 1 or > 200)
        {
            throw new ValidationException(
                "limit must be between 1 and 200",
                errorCode: "limit_out_of_range");
        }

        if (offset < 0)
        {
            throw new ValidationException(
                "offset must be greater than or equal to 0",
                errorCode: "offset_out_of_range");
        }
    }
}
