namespace DopDoc.AuthService.Infrastructure.Security;

public sealed class AuthOptions
{
    public string JwtIssuer { get; init; } = "dopdoc";
    public string JwtAudience { get; init; } = "dopdoc";
    public int AccessTokenMinutes { get; init; } = 15;
    public int RefreshTokenDays { get; init; } = 30;
    public string RefreshCookieName { get; init; } = "dopdoc_refresh_token";
    public string RefreshCookiePath { get; init; } = "/api/v1/auth";
    public string? RefreshCookieDomain { get; init; }
    public bool RefreshCookieSecure { get; init; } = true;
    public string RefreshCookieSameSite { get; init; } = "Strict";

    public string JwtSecret { get; init; } = "";
    public string RefreshPepper { get; init; } = "";
}
