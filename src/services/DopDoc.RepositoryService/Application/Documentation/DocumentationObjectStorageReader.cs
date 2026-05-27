using System.Net;
using DopDoc.Common.Errors;
using DopDoc.RepositoryService.Domain;
using Microsoft.Extensions.Options;

namespace DopDoc.RepositoryService.Application.Documentation;

public sealed class DocumentationObjectStorageOptions
{
    public string Endpoint { get; init; } = "http://localhost:9000";
    public long MaxReadableBytes { get; init; } = 20_000_000;
}

public sealed class DocumentationObjectStorageReader
{
    private readonly HttpClient _http;
    private readonly DocumentationObjectStorageOptions _options;

    public DocumentationObjectStorageReader(
        HttpClient http,
        IOptions<DocumentationObjectStorageOptions> options)
    {
        _http = http;
        _options = options.Value;
    }

    public async Task<byte[]> ReadAsync(DocumentationArtifact artifact, CancellationToken ct)
    {
        var uri = BuildObjectUri(artifact.StorageBucket, artifact.StorageKey);
        using var response = await _http.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, ct);
        if (response.StatusCode == HttpStatusCode.NotFound)
            throw ObjectNotFound(artifact);

        response.EnsureSuccessStatusCode();

        var length = response.Content.Headers.ContentLength;
        if (length is not null && length > _options.MaxReadableBytes)
            throw ObjectTooLarge(artifact, length.Value);

        var bytes = await response.Content.ReadAsByteArrayAsync(ct);
        if (bytes.LongLength > _options.MaxReadableBytes)
            throw ObjectTooLarge(artifact, bytes.LongLength);

        return bytes;
    }

    private Uri BuildObjectUri(string bucket, string key)
    {
        if (string.IsNullOrWhiteSpace(_options.Endpoint))
            throw new InvalidOperationException("ObjectStorage:Endpoint is required.");

        var endpoint = _options.Endpoint.TrimEnd('/');
        var encodedBucket = Uri.EscapeDataString(bucket);
        var encodedKey = string.Join(
            "/",
            key.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Select(Uri.EscapeDataString));

        return new Uri($"{endpoint}/{encodedBucket}/{encodedKey}", UriKind.Absolute);
    }

    private static NotFoundException ObjectNotFound(DocumentationArtifact artifact)
    {
        return new NotFoundException(
            $"Documentation object {artifact.StorageBucket}/{artifact.StorageKey} was not found.",
            errorCode: "documentation_object_not_found");
    }

    private static ValidationException ObjectTooLarge(DocumentationArtifact artifact, long size)
    {
        return new ValidationException(
            $"Documentation object {artifact.StorageBucket}/{artifact.StorageKey} is too large to read through the API.",
            errorCode: "documentation_object_too_large",
            extensions: new Dictionary<string, object?>
            {
                ["size_bytes"] = size
            });
    }
}
