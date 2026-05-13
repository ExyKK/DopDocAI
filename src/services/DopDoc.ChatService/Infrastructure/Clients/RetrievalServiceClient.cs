using System.Net.Http.Headers;
using System.Net.Http.Json;
using DopDoc.ChatService.Application.Chats;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Infrastructure.Clients;

public sealed class RetrievalServiceClient
{
    private readonly HttpClient _http;
    private readonly RetrievalOptions _options;

    public RetrievalServiceClient(HttpClient http, IOptions<RetrievalOptions> options)
    {
        _http = http;
        _options = options.Value;
        _http.BaseAddress = new Uri(_options.BaseUrl.TrimEnd('/') + "/");
        _http.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);
        _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    public async Task<RetrievalSearchResponse> SearchAsync(
        Guid snapshotId,
        string query,
        int topK,
        bool includeTests,
        double? scoreThreshold,
        CancellationToken ct)
    {
        var request = new RetrievalSearchRequest(
            SnapshotId: snapshotId,
            Query: query,
            TopK: topK,
            Filters: new RetrievalFilterRequest(
                WorkspaceUnitIds: [],
                Languages: [],
                SourceScopes: [],
                ChunkKinds: [],
                PackageIds: [],
                FilePaths: [],
                IncludeTests: includeTests),
            ScoreThreshold: scoreThreshold);

        using var response = await _http.PostAsJsonAsync("internal/v1/retrieval/search", request, ct);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            throw new UpstreamServiceException(
                $"Retrieval service search failed. status={(int)response.StatusCode} body={Truncate(body, 512)}",
                errorCode: "retrieval_service_failed");
        }

        return await response.Content.ReadFromJsonAsync<RetrievalSearchResponse>(cancellationToken: ct)
               ?? throw new UpstreamServiceException(
                   "Retrieval service returned an empty response.",
                   errorCode: "retrieval_service_response_invalid");
    }

    private static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "";

        return value.Length <= maxLength ? value : value[..maxLength];
    }
}

