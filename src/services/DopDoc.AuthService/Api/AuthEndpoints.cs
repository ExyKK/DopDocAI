using DopDoc.AuthService.Api.Contracts;
using DopDoc.AuthService.Application.Auth;
using DopDoc.AuthService.Infrastructure.Security;
using Microsoft.Extensions.Options;

namespace DopDoc.AuthService.Api;

public static class AuthEndpoints
{
    public static RouteGroupBuilder MapAuthEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1/auth").WithTags("auth");

        g.MapPost("/register", async (RegisterRequest req, AuthApplicationService auth, CancellationToken ct) =>
        {
            var id = await auth.RegisterAsync(req.Email, req.Password, ct);
            return Results.Created($"/api/v1/users/{id}", new RegisterResponse(id));
        });

        g.MapPost("/login", async (
            LoginRequest req,
            HttpContext http,
            AuthApplicationService auth,
            IOptions<AuthOptions> authOptions,
            CancellationToken ct) =>
        {
            var ua = http.Request.Headers.UserAgent.ToString();
            var ip = http.Connection.RemoteIpAddress?.ToString();

            var result = await auth.LoginAsync(req.Email, req.Password, ua, ip, ct);
            WriteRefreshCookie(http, result.RefreshToken, authOptions.Value);

            return Results.Ok(new AuthTokenResponse(
                result.AccessToken,
                "bearer",
                result.ExpiresInSeconds,
                result.UserId,
                result.Email));
        });

        g.MapPost("/refresh", async (
            HttpContext http,
            AuthApplicationService auth,
            IOptions<AuthOptions> authOptions,
            CancellationToken ct) =>
        {
            var plain = GetRefreshTokenFromCookie(http, authOptions.Value);
            var ua = http.Request.Headers.UserAgent.ToString();
            var ip = http.Connection.RemoteIpAddress?.ToString();

            var result = await auth.RefreshAsync(plain, ua, ip, ct);
            WriteRefreshCookie(http, result.RefreshToken, authOptions.Value);

            return Results.Ok(new AuthTokenResponse(
                result.AccessToken,
                "bearer",
                result.ExpiresInSeconds,
                result.UserId,
                result.Email));
        });

        g.MapPost("/logout", async (
            HttpContext http,
            AuthApplicationService auth,
            IOptions<AuthOptions> authOptions,
            CancellationToken ct) =>
        {
            var plain = GetRefreshTokenFromCookie(http, authOptions.Value);
            await auth.LogoutAsync(plain, ct);
            ClearRefreshCookie(http, authOptions.Value);
            return Results.Ok(new { ok = true });
        });

        return g;
    }

    private static string GetRefreshTokenFromCookie(HttpContext http, AuthOptions options)
    {
        return http.Request.Cookies.TryGetValue(options.RefreshCookieName, out var token)
            ? token ?? string.Empty
            : string.Empty;
    }

    private static void WriteRefreshCookie(HttpContext http, string refreshToken, AuthOptions options)
    {
        http.Response.Cookies.Append(options.RefreshCookieName, refreshToken, BuildCookieOptions(options, clear: false));
    }

    private static void ClearRefreshCookie(HttpContext http, AuthOptions options)
    {
        http.Response.Cookies.Delete(options.RefreshCookieName, BuildCookieOptions(options, clear: true));
    }

    private static CookieOptions BuildCookieOptions(AuthOptions options, bool clear)
    {
        return new CookieOptions
        {
            HttpOnly = true,
            Secure = options.RefreshCookieSecure,
            SameSite = ParseSameSite(options.RefreshCookieSameSite),
            Domain = options.RefreshCookieDomain,
            Path = options.RefreshCookiePath,
            Expires = clear ? DateTimeOffset.UnixEpoch : DateTimeOffset.UtcNow.AddDays(options.RefreshTokenDays),
            IsEssential = true
        };
    }

    private static SameSiteMode ParseSameSite(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return SameSiteMode.Strict;

        return Enum.TryParse<SameSiteMode>(value, ignoreCase: true, out var parsed)
            ? parsed
            : SameSiteMode.Strict;
    }
}
