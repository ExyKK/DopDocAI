using DopDoc.AuthService.Api.Contracts;
using DopDoc.AuthService.Application.Auth;

namespace DopDoc.AuthService.Api;

public static class AuthEndpoints
{
    public static RouteGroupBuilder MapAuthEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/auth").WithTags("auth");

        g.MapPost("/register", async (RegisterRequest req, AuthApplicationService auth, CancellationToken ct) =>
        {
            try
            {
                var id = await auth.RegisterAsync(req.Email, req.Password, ct);
                return Results.Created($"/users/{id}", new { id });
            }
            catch (ArgumentException ex)
            {
                return Results.BadRequest(new { error = ex.Message });
            }
            catch (InvalidOperationException ex)
            {
                return Results.Conflict(new { error = ex.Message });
            }
        });

        g.MapPost("/login", async (LoginRequest req, HttpContext http, AuthApplicationService auth, CancellationToken ct) =>
        {
            try
            {
                var ua = http.Request.Headers.UserAgent.ToString();
                var ip = http.Connection.RemoteIpAddress?.ToString();
                var result = await auth.LoginAsync(req.Email, req.Password, ua, ip, ct);
                return Results.Ok(new TokenResponse(result.AccessToken, result.RefreshToken, result.ExpiresInSeconds));
            }
            catch (UnauthorizedAccessException)
            {
                return Results.Unauthorized();
            }
        });

        g.MapPost("/refresh", async (HttpContext http, AuthApplicationService auth, CancellationToken ct) =>
        {
            var plain = http.Request.Headers["X-Refresh-Token"].ToString();
            if (string.IsNullOrWhiteSpace(plain)) 
                return Results.BadRequest(new { error = "Missing X-Refresh-Token" });

            try
            {
                var ua = http.Request.Headers.UserAgent.ToString();
                var ip = http.Connection.RemoteIpAddress?.ToString();
                var result = await auth.RefreshAsync(plain, ua, ip, ct);
                return Results.Ok(new TokenResponse(result.AccessToken, result.RefreshToken, result.ExpiresInSeconds));
            }
            catch (UnauthorizedAccessException)
            {
                return Results.Unauthorized();
            }
        });

        g.MapPost("/logout", async (HttpContext http, AuthApplicationService auth, CancellationToken ct) =>
        {
            var plain = http.Request.Headers["X-Refresh-Token"].ToString();
            if (string.IsNullOrWhiteSpace(plain)) 
                return Results.Ok(new { ok = true });

            await auth.LogoutAsync(plain, ct);
            return Results.Ok(new { ok = true });
        });

        return g;
    }
}