using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Repositories;
using Microsoft.AspNetCore.Mvc;

namespace DopDoc.RepositoryService.Api;

public static class RepositoryInternalEndpoints
{
    public static RouteGroupBuilder MapRepositoryInternalEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/internal/v1/repositories").WithTags("internal-repositories");

        g.MapPost("/{repository_id:guid}/snapshots", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            UpsertRepositorySnapshotRequest request,
            RepositorySnapshotApplicationService snapshots,
            CancellationToken ct) =>
        {
            var result = await snapshots.UpsertAsync(
                repositoryId,
                RepositoryContractMapper.ToCommand(request),
                ct);

            var response = RepositoryContractMapper.ToResponse(result.Snapshot);
            return result.Created
                ? Results.Created($"/internal/v1/repositories/{repositoryId}/snapshots/{response.Id}", response)
                : Results.Ok(response);
        })
        .WithName("InternalUpsertRepositorySnapshot");

        g.MapGet("/{repository_id:guid}/snapshots/by-commit/{commit_sha}", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            [FromRoute(Name = "commit_sha")] string commitSha,
            RepositorySnapshotApplicationService snapshots,
            CancellationToken ct) =>
        {
            var snapshot = await snapshots.GetByCommitAsync(repositoryId, commitSha, ct);
            return TypedResults.Ok(RepositoryContractMapper.ToResponse(snapshot));
        })
        .WithName("InternalGetRepositorySnapshotByCommit");

        g.MapPost("/{repository_id:guid}/snapshots/{snapshot_id:guid}/activate", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            [FromRoute(Name = "snapshot_id")] Guid snapshotId,
            RepositorySnapshotApplicationService snapshots,
            CancellationToken ct) =>
        {
            var snapshot = await snapshots.ActivateAsync(repositoryId, snapshotId, ct);
            return TypedResults.Ok(RepositoryContractMapper.ToResponse(snapshot));
        })
        .WithName("InternalActivateRepositorySnapshot");

        g.MapPost("/{repository_id:guid}/snapshots/{snapshot_id:guid}/analysis-artifacts", async (
            [FromRoute(Name = "repository_id")] Guid repositoryId,
            [FromRoute(Name = "snapshot_id")] Guid snapshotId,
            UpsertAnalysisArtifactRequest request,
            AnalysisArtifactApplicationService artifacts,
            CancellationToken ct) =>
        {
            var result = await artifacts.UpsertAsync(
                repositoryId,
                snapshotId,
                RepositoryContractMapper.ToCommand(request),
                ct);

            var response = RepositoryContractMapper.ToResponse(result.Artifact);
            return result.Created
                ? Results.Created($"/internal/v1/repositories/{repositoryId}/snapshots/{snapshotId}/analysis-artifacts/{response.Id}", response)
                : Results.Ok(response);
        })
        .WithName("InternalUpsertAnalysisArtifact");

        return g;
    }
}
