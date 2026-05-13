namespace DopDoc.ChatService.Infrastructure.Llm;

public sealed record LlmChatMessage(string Role, string Content);

public sealed record ChatCompletionResult(
    string Content,
    string Model,
    string Provider,
    string? FinishReason,
    int? PromptTokens,
    int? CompletionTokens
);

public interface IChatCompletionProvider
{
    Task<ChatCompletionResult> GenerateAsync(
        IReadOnlyList<LlmChatMessage> messages,
        CancellationToken ct);
}

