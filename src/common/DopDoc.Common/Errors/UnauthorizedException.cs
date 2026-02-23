using System.Net;

namespace DopDoc.Common.Errors;

public sealed class UnauthorizedException : DopDocException
{
    public UnauthorizedException(
        string message = "Unauthorized",
        string? errorCode = "unauthorized",
        IReadOnlyDictionary<string, object?>? extensions = null,
        Exception? inner = null)
        : base((int)HttpStatusCode.Unauthorized, "Unauthorized", "https://httpstatuses.com/401",
            message, errorCode, inner, extensions)
    { }
}