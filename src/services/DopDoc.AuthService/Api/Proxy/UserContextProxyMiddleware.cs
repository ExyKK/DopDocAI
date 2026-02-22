using System.Security.Claims;

namespace DopDoc.AuthService.Api.Proxy;

public sealed class UserContextProxyMiddleware : IMiddleware
{
    public Task InvokeAsync(HttpContext context, RequestDelegate next)
    {
        if (context.User?.Identity?.IsAuthenticated != true)
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return Task.CompletedTask;
        }

        // sub (preferred) or NameIdentifier
        var userId = context.User.FindFirstValue("sub")
                     ?? context.User.FindFirstValue(ClaimTypes.NameIdentifier);

        if (string.IsNullOrWhiteSpace(userId))
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return Task.CompletedTask;
        }

        context.Request.Headers[ProxyUserHeaders.UserId] = userId;

        var email = context.User.FindFirstValue("email")
                    ?? context.User.FindFirstValue(ClaimTypes.Email);

        if (!string.IsNullOrWhiteSpace(email))
            context.Request.Headers[ProxyUserHeaders.UserEmail] = email;

        return next(context);
    }
}