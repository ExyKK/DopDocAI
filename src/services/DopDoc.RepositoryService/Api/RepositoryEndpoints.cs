using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Jobs;
using DopDoc.RepositoryService.Application.Repositories;
using Microsoft.AspNetCore.Mvc;

namespace DopDoc.RepositoryService.Api;

public static class RepositoryEndpoints
{
    public static RouteGroupBuilder MapRepositoryEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1/repositories").WithTags("repositories");

        g.MapPost("/index", async (
            IndexRepositoryRequest request,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var result = await jobs.CreateIndexRunAsync(
                userId,
                request.RepositoryUrl,
                request.SelectedBranch,
                ct);

            var response = RunContractMapper.ToAcceptedResponse(result.Run);
            return Results.Accepted(response.StatusUrl, response);
        })
        .WithName("IndexRepository");

        g.MapGet("", async (
            [FromQuery] int? limit,
            [FromQuery] int? offset,
            IUserContextAccessor userContext,
            RepositoryApplicationService repositories,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var pagination = RepositoryPagination.Validate(limit, offset);
            var page = await repositories.ListAsync(
                userId,
                pagination,
                ct);

            return TypedResults.Ok(RepositoryContractMapper.ToPagedResponse(page));
        })
        .WithName("ListRepositories");

        g.MapGet("/{repository_id:guid}", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            IUserContextAccessor userContext,
            RepositoryApplicationService repositories,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var repository = await repositories.GetAsync(userId, repositoryId, ct);
            return TypedResults.Ok(RepositoryContractMapper.ToResponse(repository));
        })
        .WithName("GetRepository");

        g.MapGet("/{repository_id:guid}/snapshots", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            [FromQuery] int? limit,
            [FromQuery] int? offset,
            IUserContextAccessor userContext,
            RepositorySnapshotApplicationService snapshots,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var pagination = RepositoryPagination.Validate(limit, offset);
            var page = await snapshots.ListAsync(userId, repositoryId, pagination, ct);
            return TypedResults.Ok(RepositoryContractMapper.ToPagedResponse(page));
        })
        .WithName("ListRepositorySnapshots");

        g.MapGet("/{repository_id:guid}/snapshots/{snapshot_id:guid}", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            [FromRoute(Name = "snapshot_id")] Guid snapshotId,
            IUserContextAccessor userContext,
            RepositorySnapshotApplicationService snapshots,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var snapshot = await snapshots.GetAsync(userId, repositoryId, snapshotId, ct);
            return TypedResults.Ok(RepositoryContractMapper.ToResponse(snapshot));
        })
        .WithName("GetRepositorySnapshot");

        g.MapPost("/{repository_id:guid}/documentation", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            CreateDocumentationRunRequest request,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            var result = await jobs.CreateDocumentationRunAsync(
                userId,
                repositoryId,
                RunContractMapper.ToCommand(request),
                ct);

            var response = RunContractMapper.ToAcceptedResponse(result.Run);
            return Results.Accepted(response.StatusUrl, response);
        })
        .WithName("CreateDocumentationRun");

        return g;
    }
}
