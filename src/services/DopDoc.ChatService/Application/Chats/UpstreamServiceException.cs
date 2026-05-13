using System.Net;
using DopDoc.Common.Errors;

namespace DopDoc.ChatService.Application.Chats;

public sealed class UpstreamServiceException : DopDocException
{
    public UpstreamServiceException(
        string message,
        string? errorCode = "upstream_service_failed",
        Exception? inner = null)
        : base(
            (int)HttpStatusCode.BadGateway,
            "Bad gateway",
            "https://httpstatuses.com/502",
            message,
            errorCode,
            inner)
    { }
}

