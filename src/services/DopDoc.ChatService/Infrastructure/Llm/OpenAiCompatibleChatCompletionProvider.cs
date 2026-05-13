using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using DopDoc.ChatService.Application.Chats;
using Microsoft.Extensions.Options;

namespace DopDoc.ChatService.Infrastructure.Llm;

public sealed class OpenAiCompatibleChatCompletionProvider : IChatCompletionProvider
{
    private readonly HttpClient _http;
    private readonly LlmOptions _options;

    public OpenAiCompatibleChatCompletionProvider(HttpClient http, IOptions<LlmOptions> options)
    {
        _http = http;
        _options = options.Value;
        _http.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);
        _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    public async Task<ChatCompletionResult> GenerateAsync(
        IReadOnlyList<LlmChatMessage> messages,
        CancellationToken ct)
    {
        var request = new OpenAiChatCompletionRequest(
            Model: _options.Model,
            Messages: messages.Select(x => new OpenAiChatMessage(x.Role, x.Content)).ToList(),
            Temperature: _options.Temperature,
            MaxTokens: _options.MaxTokens,
            TopP: _options.TopP,
            RepetitionPenalty: _options.RepetitionPenalty);

        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, _options.Endpoint)
        {
            Content = JsonContent.Create(request)
        };
        httpRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _options.ApiKey);
        httpRequest.Headers.TryAddWithoutValidation("HTTP-Referer", "http://localhost");
        httpRequest.Headers.TryAddWithoutValidation("X-Title", "DopDocAI");

        using var response = await _http.SendAsync(httpRequest, ct);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            throw new UpstreamServiceException(
                $"LLM provider request failed. status={(int)response.StatusCode} body={Truncate(body, 512)}",
                errorCode: "llm_provider_failed");
        }

        var completion = await response.Content.ReadFromJsonAsync<OpenAiChatCompletionResponse>(cancellationToken: ct);
        var choice = completion?.Choices?.FirstOrDefault();
        var content = choice?.Message.Content;

        if (string.IsNullOrWhiteSpace(content))
        {
            throw new UpstreamServiceException(
                "LLM provider response did not contain message content.",
                errorCode: "llm_response_invalid");
        }

        return new ChatCompletionResult(
            Content: content,
            Model: completion?.Model ?? _options.Model,
            Provider: _options.Provider,
            FinishReason: choice?.FinishReason,
            PromptTokens: completion?.Usage?.PromptTokens,
            CompletionTokens: completion?.Usage?.CompletionTokens);
    }

    private static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "";

        return value.Length <= maxLength ? value : value[..maxLength];
    }
}

public sealed record OpenAiChatCompletionRequest(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("messages")] IReadOnlyList<OpenAiChatMessage> Messages,
    [property: JsonPropertyName("temperature")] double Temperature,
    [property: JsonPropertyName("max_tokens")] int MaxTokens,
    [property: JsonPropertyName("top_p")] double TopP,
    [property: JsonPropertyName("repetition_penalty")] double? RepetitionPenalty
);

public sealed record OpenAiChatMessage(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content")] string Content
);

public sealed record OpenAiChatCompletionResponse(
    [property: JsonPropertyName("model")] string? Model,
    [property: JsonPropertyName("choices")] IReadOnlyList<OpenAiChoice>? Choices,
    [property: JsonPropertyName("usage")] OpenAiUsage? Usage
);

public sealed record OpenAiChoice(
    [property: JsonPropertyName("message")] OpenAiMessage Message,
    [property: JsonPropertyName("finish_reason")] string? FinishReason
);

public sealed record OpenAiMessage(
    [property: JsonPropertyName("content")] string? Content
);

public sealed record OpenAiUsage(
    [property: JsonPropertyName("prompt_tokens")] int? PromptTokens,
    [property: JsonPropertyName("completion_tokens")] int? CompletionTokens,
    [property: JsonPropertyName("total_tokens")] int? TotalTokens
);
