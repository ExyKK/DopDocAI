namespace DopDoc.Common.Messaging;

public sealed class MessagingOptions
{
    public string RabbitMqUrl { get; init; } = "";
    public string CommandsExchange { get; init; } = "dopdoc.commands";
    public string EventsExchange { get; init; } = "dopdoc.events";
}
