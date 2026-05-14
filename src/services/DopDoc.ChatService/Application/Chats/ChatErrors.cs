using DopDoc.Common.Errors;

namespace DopDoc.ChatService.Application.Chats;

public static class ChatErrors
{
    public static NotFoundException NotFound(Guid chatId)
    {
        return new NotFoundException(
            $"Chat {chatId} was not found.",
            errorCode: "chat_not_found");
    }
}

