namespace DopDoc.EdgeGateway.Infrastructure.Security;

public sealed class GatewayAuthOptions
{
    public string JwtIssuer { get; init; } = "dopdoc";
    public string JwtAudience { get; init; } = "dopdoc";
    public string JwtSecret { get; init; } = "";
}
