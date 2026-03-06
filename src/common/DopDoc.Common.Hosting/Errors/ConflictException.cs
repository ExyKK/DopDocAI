using System.Net;

namespace DopDoc.Common.Errors;

public sealed class ConflictException : DopDocException
{
    public ConflictException(
        string message,
        string? errorCode = "conflict",
        IReadOnlyDictionary<string, object?>? extensions = null,
        Exception? inner = null)
        : base((int)HttpStatusCode.Conflict, "Conflict", "https://httpstatuses.com/409",
            message, errorCode, inner, extensions)
    { }
}