namespace DopDoc.Common.UserContext;

public sealed record CurrentUserContext(Guid UserId, string? Email);
