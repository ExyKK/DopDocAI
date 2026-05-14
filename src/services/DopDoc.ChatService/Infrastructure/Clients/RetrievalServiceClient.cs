using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using DopDoc.ChatService.Application.Chats;
using DopDoc.ChatService.Application.Retrieval;
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

    public async Task<RetrievedSourcePack> SearchAsync(
        Guid snapshotId,
        string query,
        CancellationToken ct)
    {
        var request = new RetrievalSearchRequest(
            SnapshotId: snapshotId,
            Query: query,
            TopK: _options.TopK,
            Filters: new RetrievalFilterRequest(
                WorkspaceUnitIds: [],
                Languages: [],
                SourceScopes: [],
                ChunkKinds: [],
                PackageIds: [],
                FilePaths: [],
                IncludeTests: _options.IncludeTests),
            ScoreThreshold: _options.ScoreThreshold);

        using var response = await _http.PostAsJsonAsync("internal/v1/retrieval/search", request, ct);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            throw new UpstreamServiceException(
                $"Retrieval service search failed. status={(int)response.StatusCode} body={Truncate(body, 512)}",
                errorCode: "retrieval_service_failed");
        }

        var result = await response.Content.ReadFromJsonAsync<RetrievalSearchResponse>(cancellationToken: ct)
                     ?? throw new UpstreamServiceException(
                         "Retrieval service returned an empty response.",
                         errorCode: "retrieval_service_response_invalid");

        return new RetrievedSourcePack(
            SnapshotId: result.SnapshotId,
            Query: result.Query,
            Sources: (result.Matches ?? []).Select(MapSource).ToList());
    }

    private static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "";

        return value.Length <= maxLength ? value : value[..maxLength];
    }

    private static RetrievedSource MapSource(RetrievalMatch match, int index)
    {
        return new RetrievedSource(
            Ordinal: index + 1,
            ChunkId: match.ChunkId,
            Score: match.Score,
            Text: match.Text,
            Location: new RetrievedSourceLocation(
                RepositoryId: match.Source.RepositoryId,
                SnapshotId: match.Source.SnapshotId,
                CommitSha: match.Source.CommitSha,
                FilePath: match.Source.FilePath,
                Language: match.Source.Language,
                SourceScope: match.Source.SourceScope,
                IsTest: match.Source.IsTest,
                StartLine: match.Source.StartLine,
                EndLine: match.Source.EndLine,
                WorkspaceUnitId: match.Source.WorkspaceUnitId),
            Entity: new RetrievedSourceEntity(
                Kind: match.Entity.Kind,
                ChunkKind: match.Entity.ChunkKind,
                Name: match.Entity.Name,
                SymbolId: match.Entity.SymbolId,
                SymbolSignature: match.Entity.SymbolSignature));
    }
}

internal sealed record RetrievalSearchRequest(
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("query")] string Query,
    [property: JsonPropertyName("top_k")] int TopK,
    [property: JsonPropertyName("filters")] RetrievalFilterRequest Filters,
    [property: JsonPropertyName("score_threshold")] double? ScoreThreshold
);

internal sealed record RetrievalFilterRequest(
    [property: JsonPropertyName("workspace_unit_ids")] IReadOnlyList<string> WorkspaceUnitIds,
    [property: JsonPropertyName("languages")] IReadOnlyList<string> Languages,
    [property: JsonPropertyName("source_scopes")] IReadOnlyList<string> SourceScopes,
    [property: JsonPropertyName("chunk_kinds")] IReadOnlyList<string> ChunkKinds,
    [property: JsonPropertyName("package_ids")] IReadOnlyList<string> PackageIds,
    [property: JsonPropertyName("file_paths")] IReadOnlyList<string> FilePaths,
    [property: JsonPropertyName("include_tests")] bool IncludeTests
);

internal sealed record RetrievalSearchResponse(
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("query")] string Query,
    [property: JsonPropertyName("matches")] IReadOnlyList<RetrievalMatch>? Matches
);

internal sealed record RetrievalMatch(
    [property: JsonPropertyName("chunk_id")] string ChunkId,
    [property: JsonPropertyName("score")] double Score,
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("source")] RetrievalSource Source,
    [property: JsonPropertyName("entity")] RetrievalEntity Entity
);

internal sealed record RetrievalSource(
    [property: JsonPropertyName("repository_id")] Guid RepositoryId,
    [property: JsonPropertyName("snapshot_id")] Guid SnapshotId,
    [property: JsonPropertyName("commit_sha")] string CommitSha,
    [property: JsonPropertyName("file_path")] string FilePath,
    [property: JsonPropertyName("language")] string Language,
    [property: JsonPropertyName("source_scope")] string SourceScope,
    [property: JsonPropertyName("is_test")] bool IsTest,
    [property: JsonPropertyName("start_line")] int? StartLine,
    [property: JsonPropertyName("end_line")] int? EndLine,
    [property: JsonPropertyName("workspace_unit_id")] string? WorkspaceUnitId
);

internal sealed record RetrievalEntity(
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("chunk_kind")] string ChunkKind,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("symbol_id")] string? SymbolId,
    [property: JsonPropertyName("symbol_signature")] string? SymbolSignature
);
