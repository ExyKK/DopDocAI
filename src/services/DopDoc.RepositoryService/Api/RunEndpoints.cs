using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Application.Jobs;
using Microsoft.AspNetCore.Mvc;

namespace DopDoc.RepositoryService.Api;

public static class RunEndpoints
{
    public static RouteGroupBuilder MapRunEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1").WithTags("runs");

        g.MapGet("/index-runs/{index_run_id:guid}", async (
            [FromRoute(Name = "index_run_id")] Guid indexRunId,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var run = await jobs.GetIndexRunAsync(userId, indexRunId, ct);
            return TypedResults.Ok(RunContractMapper.ToResponse(run));
        })
        .WithName("GetIndexRun");

        g.MapGet("/documentation-runs/{documentation_run_id:guid}", async (
            [FromRoute(Name = "documentation_run_id")] Guid documentationRunId,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var run = await jobs.GetDocumentationRunAsync(userId, documentationRunId, ct);
            return TypedResults.Ok(RunContractMapper.ToResponse(run));
        })
        .WithName("GetDocumentationRun");

        return g;
    }
}
