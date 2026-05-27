using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Jobs;
using DopDoc.RepositoryService.Domain;

namespace DopDoc.RepositoryService.Api;

internal static class RunContractMapper
{
    public static RunAcceptedResponse ToAcceptedResponse(IndexRun run)
    {
        return new RunAcceptedResponse(
            Id: run.Id,
            Kind: JobRunKinds.Index,
            Status: run.Status,
            Stage: run.Stage,
            RepositoryId: run.RepositoryId,
            SnapshotId: run.SnapshotId,
            StatusUrl: $"/api/v1/index-runs/{run.Id}",
            StreamUrl: $"/api/v1/index-runs/{run.Id}/stream");
    }

    public static RunAcceptedResponse ToAcceptedResponse(DocumentationRun run)
    {
        return new RunAcceptedResponse(
            Id: run.Id,
            Kind: JobRunKinds.Documentation,
            Status: run.Status,
            Stage: run.Stage,
            RepositoryId: run.RepositoryId,
            SnapshotId: run.SnapshotId,
            StatusUrl: $"/api/v1/documentation-runs/{run.Id}",
            StreamUrl: $"/api/v1/documentation-runs/{run.Id}/stream");
    }

    public static IndexRunResponse ToResponse(IndexRun run)
    {
        return new IndexRunResponse(
            Id: run.Id,
            RepositoryId: run.RepositoryId,
            SnapshotId: run.SnapshotId,
            TriggerKind: run.TriggerKind,
            Status: run.Status,
            Stage: run.Stage,
            ProgressPct: run.ProgressPct,
            ProgressCurrent: run.ProgressCurrent,
            ProgressTotal: run.ProgressTotal,
            Attempt: run.Attempt,
            MaxAttempts: run.MaxAttempts,
            ErrorCode: run.ErrorCode,
            ErrorMessage: run.ErrorMessage,
            EmbeddingModel: run.EmbeddingModel,
            VectorSize: run.VectorSize,
            FilesProcessed: run.FilesProcessed,
            ChunksTotal: run.ChunksTotal,
            SymbolsTotal: run.SymbolsTotal,
            VectorsUpserted: run.VectorsUpserted,
            StartedAt: run.StartedAt,
            FinishedAt: run.FinishedAt,
            CreatedAt: run.CreatedAt,
            UpdatedAt: run.UpdatedAt);
    }

    public static DocumentationRunResponse ToResponse(DocumentationRun run)
    {
        var effectiveTemplateKind = string.IsNullOrWhiteSpace(run.EffectiveTemplateKind)
            ? null
            : run.EffectiveTemplateKind;

        return new DocumentationRunResponse(
            Id: run.Id,
            RepositoryId: run.RepositoryId,
            SnapshotId: run.SnapshotId,
            SourceIndexRunId: run.SourceIndexRunId,
            BaseSnapshotId: run.BaseSnapshotId,
            TemplateKind: effectiveTemplateKind ?? run.TemplateKind,
            RequestedTemplateKind: run.TemplateKind,
            EffectiveTemplateKind: effectiveTemplateKind,
            Status: run.Status,
            Stage: run.Stage,
            ProgressPct: run.ProgressPct,
            ProgressCurrent: run.ProgressCurrent,
            ProgressTotal: run.ProgressTotal,
            Attempt: run.Attempt,
            MaxAttempts: run.MaxAttempts,
            ModelName: run.ModelName,
            ErrorCode: run.ErrorCode,
            ErrorMessage: run.ErrorMessage,
            PublishedManifestArtifactId: run.PublishedManifestArtifactId,
            StartedAt: run.StartedAt,
            FinishedAt: run.FinishedAt,
            CreatedAt: run.CreatedAt,
            UpdatedAt: run.UpdatedAt);
    }

    public static PagedResponse<IndexRunResponse> ToPagedResponse(PagedIndexRunResult page)
    {
        return new PagedResponse<IndexRunResponse>(
            Items: page.Items.Select(ToResponse).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.HasMore,
            TotalCount: page.TotalCount);
    }

    public static PagedResponse<DocumentationRunResponse> ToPagedResponse(PagedDocumentationRunResult page)
    {
        return new PagedResponse<DocumentationRunResponse>(
            Items: page.Items.Select(ToResponse).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.HasMore,
            TotalCount: page.TotalCount);
    }

    public static CreateDocumentationRunCommand ToCommand(CreateDocumentationRunRequest request)
    {
        return new CreateDocumentationRunCommand(
            SnapshotId: request.SnapshotId,
            TemplateKind: request.TemplateKind,
            BaseSnapshotId: request.BaseSnapshotId);
    }
}
