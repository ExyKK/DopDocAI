using System.Text;
using System.Text.RegularExpressions;
using DopDoc.ChatService.Domain;
using DopDoc.ChatService.Infrastructure.Clients;

namespace DopDoc.ChatService.Application.Chats;

public static class ChatPromptBuilder
{
    public const string PromptVersion = "chat-rag-v1";
    private static readonly Regex CitationRegex = new(
        @"\[(?<body>\d+(?:\s*,\s*\d+)*)\]",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);

    public static IReadOnlyList<PromptSource> BuildPromptSources(
        IReadOnlyList<RetrievalMatch> matches,
        int maxTotalChars)
    {
        var sources = new List<PromptSource>();
        var remaining = Math.Max(0, maxTotalChars);

        for (var index = 0; index < matches.Count; index++)
        {
            if (remaining <= 0)
                break;

            var match = matches[index];
            var text = match.Text.Trim();
            if (text.Length > remaining)
                text = text[..remaining];

            sources.Add(new PromptSource(index + 1, match, text));
            remaining -= text.Length;
        }

        return sources;
    }

    public static string BuildRepositoryContext(IReadOnlyList<PromptSource> sources)
    {
        if (sources.Count == 0)
            return "No retrieval sources were found for this question.";

        var sb = new StringBuilder();
        foreach (var source in sources)
        {
            if (sb.Length > 0)
                sb.AppendLine().AppendLine("---").AppendLine();

            var match = source.Match;
            var location = FormatLocation(match.Source.StartLine, match.Source.EndLine);
            var entity = string.IsNullOrWhiteSpace(match.Entity.Name)
                ? match.Entity.ChunkKind
                : $"{match.Entity.ChunkKind}: {match.Entity.Name}";

            sb.Append('[').Append(source.Ordinal).Append("] ")
                .Append(match.Source.FilePath);

            if (!string.IsNullOrWhiteSpace(location))
                sb.Append(' ').Append(location);

            sb.Append(" (")
                .Append(match.Source.Language)
                .Append(", ")
                .Append(entity)
                .AppendLine(")");

            sb.Append(source.Text);
        }

        return sb.ToString();
    }

    public static string BuildSourceRules(string repositoryContext)
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

    public static IReadOnlySet<int> ExtractCitedOrdinals(string answer, int maxOrdinal)
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

    public static ChatMessageSource ToMessageSource(
        Guid assistantMessageId,
        PromptSource source,
        IReadOnlySet<int> citedOrdinals)
    {
        var match = source.Match;
        var kind = string.IsNullOrWhiteSpace(match.Entity.Kind) ? "chunk" : match.Entity.Kind;

        return new ChatMessageSource
        {
            MessageId = assistantMessageId,
            Ordinal = source.Ordinal,
            SnapshotId = match.Source.SnapshotId,
            SourceKind = kind,
            FilePath = match.Source.FilePath,
            SymbolName = match.Entity.Name,
            StartLine = match.Source.StartLine,
            EndLine = match.Source.EndLine,
            ChunkId = match.ChunkId,
            Score = match.Score,
            UsedInAnswer = citedOrdinals.Contains(source.Ordinal),
            CitationLabel = $"[{source.Ordinal}]"
        };
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
    RetrievalMatch Match,
    string Text
);
