namespace DopDoc.AuthService.Application.Auth;

public sealed record AuthResult(string AccessToken, string RefreshToken, int ExpiresInSeconds);