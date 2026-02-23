using System.Net;

namespace DopDoc.Common.Errors;

public sealed class NotFoundException : DopDocException
{
    public NotFoundException(
        string message,
        string? errorCode = "not_found",
        IReadOnlyDictionary<string, object?>? extensions = null,
        Exception? inner = null)
        : base((int)HttpStatusCode.NotFound, "Not found", "https://httpstatuses.com/404",
            message, errorCode, inner, extensions)
    { }
}