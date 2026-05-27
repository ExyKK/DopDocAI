using DopDoc.Common.UserContext;
using DopDoc.RepositoryService.Application.Documentation;
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

        g.MapGet("/documentation-runs/{documentation_run_id:guid}/artifacts", async (
            [FromRoute(Name = "documentation_run_id")] Guid documentationRunId,
            [FromQuery(Name = "attempt")] int? attempt,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            DocumentationArtifactApplicationService artifacts,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            await jobs.GetDocumentationRunAsync(userId, documentationRunId, ct);
            var result = await artifacts.ListAsync(documentationRunId, attempt, ct);
            return TypedResults.Ok(result.Select(DocumentationContractMapper.ToResponse).ToList());
        })
        .WithName("ListDocumentationArtifacts");

        g.MapGet("/documentation-runs/{documentation_run_id:guid}/artifacts/{artifact_id:guid}/content", async (
            [FromRoute(Name = "documentation_run_id")] Guid documentationRunId,
            [FromRoute(Name = "artifact_id")] Guid artifactId,
            IUserContextAccessor userContext,
            JobRunApplicationService jobs,
            DocumentationArtifactApplicationService artifacts,
            DocumentationObjectStorageReader objectStorage,
            CancellationToken ct) =>
        {
            var userId = userContext.GetRequiredUserId();
            await jobs.GetDocumentationRunAsync(userId, documentationRunId, ct);
            var artifact = await artifacts.GetAsync(documentationRunId, artifactId, ct);
            var content = await objectStorage.ReadAsync(artifact, ct);
            return Results.File(content, artifact.ContentType);
        })
        .WithName("GetDocumentationArtifactContent");

        return g;
    }
}
