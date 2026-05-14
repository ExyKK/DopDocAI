using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using DopDoc.ChatService.Application.Chats;
using DopDoc.ChatService.Application.Snapshots;
using DopDoc.Common.Errors;
using DopDoc.Common.UserContext;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Infrastructure.Clients;

public sealed class RepositoryServiceClient
{
    private readonly HttpClient _http;
    private readonly RepositoryServiceOptions _options;

    public RepositoryServiceClient(HttpClient http, IOptions<RepositoryServiceOptions> options)
    {
        _http = http;
        _options = options.Value;
        _http.BaseAddress = new Uri(_options.BaseUrl.TrimEnd('/') + "/");
        _http.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);
        _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    public async Task<ReadySnapshotRef> GetReadySnapshotAsync(
        Guid userId,
        Guid repositoryId,
        Guid? snapshotId,
        CancellationToken ct)
    {
        var path = snapshotId is null
            ? $"api/v1/repositories/{repositoryId}/snapshots/ready"
            : $"api/v1/repositories/{repositoryId}/snapshots/ready?snapshot_id={snapshotId.Value}";

        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        AddUserContext(request, userId);

        using var response = await _http.SendAsync(request, ct);
        if (response.StatusCode == HttpStatusCode.NotFound)
            throw RepositoryNotFound(repositoryId);

        if (response.StatusCode == HttpStatusCode.Conflict)
        {
            throw new ConflictException(
                "Repository does not have a ready indexed snapshot.",
                errorCode: "repository_snapshot_not_ready");
        }

        if (!response.IsSuccessStatusCode)
            throw await UpstreamFailureAsync(response, "RepositoryService ready snapshot lookup failed.", ct);

        var snapshot = await response.Content.ReadFromJsonAsync<RepositorySnapshotResponse>(cancellationToken: ct)
                       ?? throw new UpstreamServiceException(
                           "RepositoryService returned an empty ready snapshot response.",
                           errorCode: "repository_service_response_invalid");

        return new ReadySnapshotRef(
            RepositoryId: snapshot.RepositoryId,
            SnapshotId: snapshot.Id,
            CommitSha: snapshot.CommitSha);
    }

    private static void AddUserContext(HttpRequestMessage request, Guid userId)
    {
        request.Headers.TryAddWithoutValidation(UserContextHeaderNames.UserId, userId.ToString());
    }

    private static NotFoundException RepositoryNotFound(Guid repositoryId)
    {
        return new NotFoundException(
            $"Repository {repositoryId} was not found.",
            errorCode: "repository_not_found");
    }

    private static async Task<UpstreamServiceException> UpstreamFailureAsync(
        HttpResponseMessage response,
        string message,
        CancellationToken ct)
    {
        var body = await response.Content.ReadAsStringAsync(ct);
        return new UpstreamServiceException(
            $"{message} status={(int)response.StatusCode} body={Truncate(body, 512)}",
            errorCode: "repository_service_failed");
    }

    private static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "";

        return value.Length <= maxLength ? value : value[..maxLength];
    }
}

internal sealed record RepositorySnapshotResponse(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("commit_sha")] string CommitSha
);
