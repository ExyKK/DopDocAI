namespace DopDoc.AuthService.Infrastructure.Security;

public sealed class AuthOptions
{
    public string JwtIssuer { get; init; } = "dopdoc";
    public string JwtAudience { get; init; } = "dopdoc";
    public int AccessTokenMinutes { get; init; } = 30;
    public int RefreshTokenDays { get; init; } = 30;

    public string JwtSecret { get; init; } = "";
    public string RefreshPepper { get; init; } = "";
}