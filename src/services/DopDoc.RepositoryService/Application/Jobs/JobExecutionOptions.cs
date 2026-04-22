namespace DopDoc.RepositoryService.Application.Jobs;

public sealed class JobExecutionOptions
{
    public const int DefaultMaxAttempts = 3;
    public const int DefaultLeaseSeconds = 120;
    public const int DefaultHeartbeatSeconds = 15;

    public int MaxAttempts { get; set; } = DefaultMaxAttempts;
    public int LeaseSeconds { get; set; } = DefaultLeaseSeconds;
    public int HeartbeatSeconds { get; set; } = DefaultHeartbeatSeconds;

    public TimeSpan LeaseDuration => TimeSpan.FromSeconds(LeaseSeconds);
    public TimeSpan HeartbeatInterval => TimeSpan.FromSeconds(HeartbeatSeconds);
}
