namespace DopDoc.Common.Errors;

public abstract class DopDocException : Exception
{
    /// <summary>HTTP status code for ProblemDetails.</summary>
    public int StatusCode { get; }

    /// <summary>Short human-friendly title.</summary>
    public string Title { get; }

    /// <summary>RFC/URL-ish identifier for error type.</summary>
    public string Type { get; }

    /// <summary>Optional machine-readable error code.</summary>
    public string? ErrorCode { get; }

    /// <summary>Optional extra fields that will go into ProblemDetails.Extensions.</summary>
    public IReadOnlyDictionary<string, object?>? Extensions { get; }

    protected DopDocException(
        int statusCode,
        string title,
        string type,
        string message,
        string? errorCode = null,
        Exception? inner = null,
        IReadOnlyDictionary<string, object?>? extensions = null)
        : base(message, inner)
    {
        StatusCode = statusCode;
        Title = title;
        Type = type;
        ErrorCode = errorCode;
        Extensions = extensions;
    }
}