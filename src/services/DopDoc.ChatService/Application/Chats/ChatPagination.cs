using DopDoc.Common.Errors;

namespace DopDoc.ChatService.Application.Chats;

public sealed record ChatPagination(int Limit, int Offset)
{
    public static ChatPagination Validate(int? limit, int? offset)
    {
        var normalizedLimit = limit ?? 50;
        var normalizedOffset = offset ?? 0;

        if (normalizedLimit is < 1 or > 200)
        {
            throw new ValidationException(
                "limit must be between 1 and 200",
                errorCode: "limit_out_of_range");
        }

        if (normalizedOffset < 0)
        {
            throw new ValidationException(
                "offset must be greater than or equal to 0",
                errorCode: "offset_out_of_range");
        }

        return new ChatPagination(normalizedLimit, normalizedOffset);
    }
}

