namespace DopDoc.Common.Messaging;

public interface IMessageEnvelope
{
    Guid EventId { get; }
    string EventType { get; }
    DateTimeOffset OccurredAt { get; }
    string? CorrelationId { get; }
    string? CausationId { get; }
}

public sealed record MessageEnvelope<TPayload>(
    Guid EventId,
    string EventType,
    DateTimeOffset OccurredAt,
    string? CorrelationId,
    string? CausationId,
    TPayload Payload) : IMessageEnvelope;
