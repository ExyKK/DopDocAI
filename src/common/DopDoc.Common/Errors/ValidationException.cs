using System.Net;

namespace DopDoc.Common.Errors;

public sealed class ValidationException : DopDocException
{
    public ValidationException(
        string message,
        string? errorCode = "validation_error",
        IReadOnlyDictionary<string, object?>? extensions = null,
        Exception? inner = null)
        : base((int)HttpStatusCode.BadRequest, "Bad request", "https://httpstatuses.com/400",
            message, errorCode, inner, extensions)
    { }
}