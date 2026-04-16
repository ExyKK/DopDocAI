using DopDoc.ChatService.Api.Contracts;
using DopDoc.Common.Errors;
using DopDoc.Common.UserContext;

namespace DopDoc.ChatService.Api;

public static class ChatEndpoints
{
    public static RouteGroupBuilder MapChatEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v1/chats").WithTags("chats");

        g.MapGet("", (int limit, int offset, IUserContextAccessor userContext) =>
        {
            ValidatePagination(limit, offset);
            _ = userContext.GetRequiredUserId();

            var response = new PagedResponse<ChatListItemResponse>(
                Items: [],
                Limit: limit,
                Offset: offset,
                HasMore: false,
                TotalCount: 0);

            return TypedResults.Ok(response);
        })
        .WithName("ListChats");

        return g;
    }

    private static void ValidatePagination(int limit, int offset)
    {
        if (limit is < 1 or > 200)
        {
            throw new ValidationException(
                "limit must be between 1 and 200",
                errorCode: "limit_out_of_range");
        }

        if (offset < 0)
        {
            throw new ValidationException(
                "offset must be greater than or equal to 0",
                errorCode: "offset_out_of_range");
        }
    }
}
