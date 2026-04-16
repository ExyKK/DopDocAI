using DopDoc.Common.Errors;
using Microsoft.AspNetCore.Http;

namespace DopDoc.Common.UserContext;

public sealed class HeaderUserContextAccessor : IUserContextAccessor
{
    private readonly IHttpContextAccessor _httpContextAccessor;

    public HeaderUserContextAccessor(IHttpContextAccessor httpContextAccessor)
    {
        _httpContextAccessor = httpContextAccessor;
    }

    public CurrentUserContext? CurrentUser
    {
        get
        {
            var httpContext = _httpContextAccessor.HttpContext;
            if (httpContext is null)
                return null;

            if (!httpContext.Request.Headers.TryGetValue(UserContextHeaderNames.UserId, out var userIdValues))
                return null;

            var rawUserId = userIdValues.ToString();
            if (string.IsNullOrWhiteSpace(rawUserId))
                return null;

            if (!Guid.TryParse(rawUserId, out var userId))
            {
                throw new UnauthorizedException(
                    "Invalid trusted user context header",
                    errorCode: "user_context_invalid");
            }

            var email = httpContext.Request.Headers.TryGetValue(UserContextHeaderNames.UserEmail, out var emailValues)
                ? emailValues.ToString()
                : null;

            return new CurrentUserContext(userId, string.IsNullOrWhiteSpace(email) ? null : email);
        }
    }

    public Guid? UserId => CurrentUser?.UserId;

    public string? UserEmail => CurrentUser?.Email;

    public Guid GetRequiredUserId()
    {
        var currentUser = CurrentUser;
        if (currentUser is null)
        {
            throw new UnauthorizedException(
                "Missing trusted user context header",
                errorCode: "user_context_missing");
        }

        return currentUser.UserId;
    }
}
