using System.Text;
using System.Text.RegularExpressions;
using DopDoc.ChatService.Application.Retrieval;
using DopDoc.ChatService.Domain;
using DopDoc.ChatService.Infrastructure.Llm;

namespace DopDoc.ChatService.Application.Chats;

public sealed class ChatPromptFactory
{
    public const string PromptVersion = "chat-rag-v1";
    private static readonly Regex CitationRegex = new(
        @"\[(?<body>\d+(?:\s*,\s*\d+)*)\]",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    public IReadOnlyList<PromptSource> BuildPromptSources(
        IReadOnlyList<RetrievedSource> sources,
        int maxTotalChars)
    {
        var promptSources = new List<PromptSource>();
        var remaining = Math.Max(0, maxTotalChars);

        foreach (var source in sources)
        {
            if (remaining <= 0)
                break;

            var text = source.Text.Trim();
            if (text.Length > remaining)
                text = text[..remaining];

            promptSources.Add(new PromptSource(source.Ordinal, source, text));
            remaining -= text.Length;
        }

        return promptSources;
    }

    public IReadOnlyList<LlmChatMessage> BuildMessages(
        string userContent,
        IReadOnlyList<ChatMessage> history,
        IReadOnlyList<PromptSource> sources,
        string defaultSystemPrompt)
    {
        var messages = new List<LlmChatMessage>
        {
            new(ChatRoles.System, defaultSystemPrompt),
            new(ChatRoles.System, BuildSourceRules(BuildRepositoryContext(sources)))
        };

        foreach (var message in history)
        {
            if (message.Role is ChatRoles.User or ChatRoles.Assistant)
                messages.Add(new LlmChatMessage(message.Role, message.ContentMarkdown));
        }

        messages.Add(new LlmChatMessage(ChatRoles.User, userContent));
        return messages;
    }

    public IReadOnlySet<int> ExtractCitedOrdinals(string answer, int maxOrdinal)
    {
        var result = new HashSet<int>();

        foreach (Match match in CitationRegex.Matches(answer))
        {
            var body = match.Groups["body"].Value;
            foreach (var part in body.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
            {
                if (int.TryParse(part, out var ordinal) && ordinal >= 1 && ordinal <= maxOrdinal)
                    result.Add(ordinal);
            }
        }

        return result;
    }

    public ChatMessageSource ToMessageSource(
        Guid assistantMessageId,
        PromptSource source,
        IReadOnlySet<int> citedOrdinals)
    {
        var retrieved = source.Source;
        var kind = string.IsNullOrWhiteSpace(retrieved.Entity.Kind) ? "chunk" : retrieved.Entity.Kind;

        return new ChatMessageSource
        {
            MessageId = assistantMessageId,
            Ordinal = source.Ordinal,
            SnapshotId = retrieved.Location.SnapshotId,
            SourceKind = kind,
            FilePath = retrieved.Location.FilePath,
            SymbolName = retrieved.Entity.Name,
            StartLine = retrieved.Location.StartLine,
            EndLine = retrieved.Location.EndLine,
            ChunkId = retrieved.ChunkId,
            Score = retrieved.Score,
            UsedInAnswer = citedOrdinals.Contains(source.Ordinal),
            CitationLabel = $"[{source.Ordinal}]"
        };
    }

    private static string BuildRepositoryContext(IReadOnlyList<PromptSource> sources)
    {
        if (sources.Count == 0)
            return "No retrieval sources were found for this question.";

        var sb = new StringBuilder();
        foreach (var source in sources)
        {
            if (sb.Length > 0)
                sb.AppendLine().AppendLine("---").AppendLine();

            var retrieved = source.Source;
            var location = FormatLocation(retrieved.Location.StartLine, retrieved.Location.EndLine);
            var entity = string.IsNullOrWhiteSpace(retrieved.Entity.Name)
                ? retrieved.Entity.ChunkKind
                : $"{retrieved.Entity.ChunkKind}: {retrieved.Entity.Name}";

            sb.Append('[').Append(source.Ordinal).Append("] ")
                .Append(retrieved.Location.FilePath);

            if (!string.IsNullOrWhiteSpace(location))
                sb.Append(' ').Append(location);

            sb.Append(" (")
                .Append(retrieved.Location.Language)
                .Append(", ")
                .Append(entity)
                .AppendLine(")");

            sb.Append(source.Text);
        }

        return sb.ToString();
    }

    private static string BuildSourceRules(string repositoryContext)
    {
        return
            "Answer using ONLY the repository context below and the prior chat history. " +
            "If the context does not contain the answer, say that the indexed repository context is insufficient.\n\n" +
            "Citation rules:\n" +
            "- Cite every repository fact or code claim inline with the source number, for example [1].\n" +
            "- Use only source numbers that exist in the repository context.\n" +
            "- Do not invent file paths, APIs, behavior, or citations.\n" +
            "- Prefer the user's language for the answer.\n\n" +
            "Repository context:\n" +
            repositoryContext;
    }

    private static string FormatLocation(int? startLine, int? endLine)
    {
        if (startLine is null || endLine is null)
            return "";

        return startLine == endLine
            ? $"line {startLine}"
            : $"lines {startLine}-{endLine}";
    }
}

public sealed record PromptSource(
    int Ordinal,
    RetrievedSource Source,
    string Text
);

