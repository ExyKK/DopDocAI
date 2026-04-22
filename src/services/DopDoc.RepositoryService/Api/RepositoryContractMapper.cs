using DopDoc.RepositoryService.Api.Contracts;
using DopDoc.RepositoryService.Application.Repositories;
using RepositoryEntity = DopDoc.RepositoryService.Domain.Repository;

namespace DopDoc.RepositoryService.Api;

internal static class RepositoryContractMapper
{
    public static PagedResponse<RepositoryListItemResponse> ToPagedResponse(PagedRepositoryResult page)
    {
        return new PagedResponse<RepositoryListItemResponse>(
            Items: page.Items.Select(ToListItemResponse).ToList(),
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
}
