using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Repositories;
using AnalysisArtifactEntity = DopDoc.RepositoryService.Domain.AnalysisArtifact;
using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;
using RepositorySnapshotEntity = DopDoc.RepositoryService.Domain.RepositorySnapshot;

namespace DopDoc.RepositoryService.Api;

internal static class RepositoryContractMapper
{
    public static RepositoryResponse ToResponse(RepositoryEntity repository)
    {
        return new RepositoryResponse(
            Id: repository.Id,
            Provider: repository.Provider,
            Host: repository.Host,
            Owner: repository.Owner,
            Name: repository.Name,
            FullName: repository.FullName,
            Url: repository.NormalizedUrl,
            SelectedBranch: repository.SelectedBranch,
            DefaultBranch: repository.DefaultBranch,
            ActiveSnapshotId: repository.ActiveSnapshotId,
            CreatedAt: repository.CreatedAt,
            UpdatedAt: repository.UpdatedAt);
    }
    
    public static RepositorySnapshotResponse ToResponse(RepositorySnapshotEntity snapshot)
    {
        return new RepositorySnapshotResponse(
            Id: snapshot.Id,
            RepositoryId: snapshot.RepositoryId,
            BranchName: snapshot.BranchName,
            CommitSha: snapshot.CommitSha,
            TreeHash: snapshot.TreeHash,
            CommitSubject: snapshot.CommitSubject,
            CommitMessage: snapshot.CommitMessage,
            CommitAuthorName: snapshot.CommitAuthorName,
            CommitAuthorEmail: snapshot.CommitAuthorEmail,
            CommitAuthoredAt: snapshot.CommitAuthoredAt,
            CommitCommittedAt: snapshot.CommitCommittedAt,
            FilesTotal: snapshot.FilesTotal,
            GoFilesTotal: snapshot.GoFilesTotal,
            ReadmeFilesTotal: snapshot.ReadmeFilesTotal,
            BytesTotal: snapshot.BytesTotal,
            CreatedAt: snapshot.CreatedAt);
    }

    public static AnalysisArtifactResponse ToResponse(AnalysisArtifactEntity artifact)
    {
        return new AnalysisArtifactResponse(
            Id: artifact.Id,
            SnapshotId: artifact.SnapshotId,
            ProducedByIndexRunId: artifact.ProducedByIndexRunId,
            ArtifactKind: artifact.ArtifactKind,
            StorageBucket: artifact.StorageBucket,
            StorageKey: artifact.StorageKey,
            ContentType: artifact.ContentType,
            Format: artifact.Format,
            ChecksumSha256: artifact.ChecksumSha256,
            SizeBytes: artifact.SizeBytes,
            RowCount: artifact.RowCount,
            SchemaVersion: artifact.SchemaVersion,
            CreatedAt: artifact.CreatedAt);
    }
    
    public static PagedResponse<RepositoryListItemResponse> ToPagedResponse(PagedRepositoryResult page)
    {
        return new PagedResponse<RepositoryListItemResponse>(
            Items: page.Items.Select(ToListItemResponse).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.HasMore,
            TotalCount: page.TotalCount);
    }

    public static PagedResponse<RepositorySnapshotResponse> ToPagedResponse(PagedRepositorySnapshotResult page)
    {
        return new PagedResponse<RepositorySnapshotResponse>(
            Items: page.Items.Select(ToResponse).ToList(),
            Limit: page.Limit,
            Offset: page.Offset,
            HasMore: page.HasMore,
            TotalCount: page.TotalCount);
    }
    
    private static RepositoryListItemResponse ToListItemResponse(RepositoryEntity repository)
    {
        return new RepositoryListItemResponse(
            Id: repository.Id,
            Url: repository.NormalizedUrl,
            FullName: repository.FullName,
            SelectedBranch: repository.SelectedBranch,
            DefaultBranch: repository.DefaultBranch,
            ActiveSnapshotId: repository.ActiveSnapshotId,
            CreatedAt: repository.CreatedAt);
    }

    public static UpsertRepositorySnapshotCommand ToCommand(UpsertRepositorySnapshotRequest request)
    {
        return new UpsertRepositorySnapshotCommand(
            BranchName: request.BranchName,
            CommitSha: request.CommitSha,
            TreeHash: request.TreeHash,
            CommitSubject: request.CommitSubject,
            CommitMessage: request.CommitMessage,
            CommitAuthorName: request.CommitAuthorName,
            CommitAuthorEmail: request.CommitAuthorEmail,
            CommitAuthoredAt: request.CommitAuthoredAt,
            CommitCommittedAt: request.CommitCommittedAt,
            FilesTotal: request.FilesTotal,
            GoFilesTotal: request.GoFilesTotal,
            ReadmeFilesTotal: request.ReadmeFilesTotal,
            BytesTotal: request.BytesTotal,
            SetActive: request.SetActive);
    }

    public static UpsertAnalysisArtifactCommand ToCommand(UpsertAnalysisArtifactRequest request)
    {
        return new UpsertAnalysisArtifactCommand(
            ProducedByIndexRunId: request.ProducedByIndexRunId,
            ArtifactKind: request.ArtifactKind,
            StorageBucket: request.StorageBucket,
            StorageKey: request.StorageKey,
            ContentType: request.ContentType,
            Format: request.Format,
            ChecksumSha256: request.ChecksumSha256,
            SizeBytes: request.SizeBytes,
            RowCount: request.RowCount,
            SchemaVersion: request.SchemaVersion);
    }
}
