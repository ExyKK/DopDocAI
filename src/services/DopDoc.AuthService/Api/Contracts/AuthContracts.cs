namespace DopDoc.AuthService.Api.Contracts;

public sealed record RegisterRequest(string Email, string Password);
public sealed record LoginRequest(string Email, string Password);

public sealed record TokenResponse(
    string AccessToken,
    string RefreshToken,
    int ExpiresInSeconds
);