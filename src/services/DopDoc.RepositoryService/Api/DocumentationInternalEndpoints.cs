using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Documentation;
using Microsoft.AspNetCore.Mvc;

namespace DopDoc.RepositoryService.Api;

public static class DocumentationInternalEndpoints
{
    public static RouteGroupBuilder MapDocumentationInternalEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/internal/v1/documentation-runs").WithTags("internal-documentation");

        g.MapPost("/{documentation_run_id:guid}/sections/plan", async (
            [FromRoute(Name = "documentation_run_id")] Guid documentationRunId,
            ReplaceDocumentationSectionsRequest request,
            DocumentationSectionApplicationService sections,
            CancellationToken ct) =>
        {
            var result = await sections.ReplacePlanAsync(
                documentationRunId,
                DocumentationContractMapper.ToCommand(request),
                ct);

            return TypedResults.Ok(result.Select(DocumentationContractMapper.ToResponse).ToList());
        })
        .WithName("InternalReplaceDocumentationSectionPlan");

        g.MapPost("/{documentation_run_id:guid}/artifacts", async (
            [FromRoute(Name = "documentation_run_id")] Guid documentationRunId,
            RegisterDocumentationArtifactRequest request,
            DocumentationArtifactApplicationService artifacts,
            CancellationToken ct) =>
        {
            var result = await artifacts.RegisterAsync(
                documentationRunId,
                DocumentationContractMapper.ToCommand(request),
                ct);

            return TypedResults.Ok(DocumentationContractMapper.ToResponse(result));
        })
        .WithName("InternalRegisterDocumentationArtifact");

        return g;
    }
}
