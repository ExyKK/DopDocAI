using DopDoc.Common.Errors;

namespace DopDoc.RepositoryService.Application.Jobs;

public static class JobExecutionContract
{
    public static void ValidateStatus(string status)
    {
        if (!JobRunStatuses.IsKnown(status))
        {
            throw new ValidationException(
                $"Unknown job status '{status}'.",
                errorCode: "job_status_invalid");
        }
    }

    public static void ValidateStage(string kind, string stage)
    {
        if (!JobRunKinds.All.Contains(kind))
        {
            throw new ValidationException(
                $"Unknown job kind '{kind}'.",
                errorCode: "job_kind_invalid");
        }

        if (!JobRunStages.IsKnownForKind(kind, stage))
        {
            throw new ValidationException(
                $"Unknown '{kind}' job stage '{stage}'.",
                errorCode: "job_stage_invalid");
        }
    }

    public static void ValidateProgress(int progressPct, int progressCurrent, int progressTotal)
    {
        if (progressPct is < 0 or > 100)
            throw new ValidationException("progress_pct must be between 0 and 100", errorCode: "job_progress_invalid");

        if (progressCurrent < 0 || progressTotal < 0 || progressCurrent > progressTotal)
            throw new ValidationException("progress counters are invalid", errorCode: "job_progress_invalid");
    }

    public static bool CanTransition(string currentStatus, string nextStatus)
    {
        ValidateStatus(currentStatus);
        ValidateStatus(nextStatus);

        if (currentStatus == nextStatus)
            return true;

        return currentStatus switch
        {
            JobRunStatuses.Queued => nextStatus is JobRunStatuses.Running or JobRunStatuses.Canceled,
            JobRunStatuses.Running => nextStatus is JobRunStatuses.Succeeded
                or JobRunStatuses.Failed
                or JobRunStatuses.Canceled
                or JobRunStatuses.Stale,
            JobRunStatuses.Stale => nextStatus is JobRunStatuses.Queued or JobRunStatuses.Failed,
            _ => false
        };
    }
}
