namespace DopDoc.ChatService.Infrastructure.Llm;

public sealed class StubChatCompletionProvider : IChatCompletionProvider
{
    public Task<ChatCompletionResult> GenerateAsync(
        IReadOnlyList<LlmChatMessage> messages,
        CancellationToken ct)
    {
        var userMessage = messages.LastOrDefault(x => x.Role == "user")?.Content ?? "";
        var answer =
            "LLM stub mode is enabled, so no external model was called.\n\n" +
            "Question received:\n" +
            userMessage + "\n\n" +
            "Configure `Llm:Provider=openai_compatible` and `Llm:ApiKey` to get a real grounded answer over the retrieved repository context.";

        return Task.FromResult(new ChatCompletionResult(
            Content: answer,
            Model: "stub",
            Provider: "stub",
            FinishReason: "stop",
            PromptTokens: null,
            CompletionTokens: null));
    }
}

