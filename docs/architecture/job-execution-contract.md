# Job Execution Contract

## Purpose

Этот документ фиксирует общий lifecycle для тяжелых задач DopDocAI. Один и тот же contract применяется к:

- `index_runs` в `RepositoryService`;
- `documentation_runs` в `RepositoryService`;
- будущим Python workers: `ingestion_service` и `documentation_service`.

Таблицы остаются доменно раздельными, но execution semantics должны быть одинаковыми.

## Statuses

Разрешенные значения `status`:

- `queued` — задача создана и доступна для claim worker-ом.
- `running` — задача взята worker-ом, lease активен.
- `succeeded` — задача завершилась успешно.
- `failed` — задача завершилась ошибкой и больше не будет автоматически выполняться.
- `canceled` — задача отменена штатно.
- `stale` — задача потеряла heartbeat/lease и ожидает recovery decision.

Активные статусы: `queued`, `running`.

Терминальные статусы: `succeeded`, `failed`, `canceled`, `stale`.

Разрешенные переходы:

- `queued -> running`
- `queued -> canceled`
- `running -> succeeded`
- `running -> failed`
- `running -> canceled`
- `running -> stale`
- `stale -> queued`
- `stale -> failed`

Повторная запись того же статуса идемпотентна.

## Shared Fields

Обе run-таблицы используют одинаковую execution-группу полей:

- `status` — одно из значений выше.
- `stage` — текущий этап внутри конкретного типа задачи.
- `progress_pct` — значение от `0` до `100`.
- `progress_current` и `progress_total` — детальные counters для текущего stage.
- `attempt` — текущий номер попытки.
- `max_attempts` — максимальное количество попыток.
- `worker_id` — уникальный идентификатор worker instance.
- `lease_until` — время, до которого worker владеет задачей.
- `heartbeat_at` — последнее подтверждение жизни worker-а.
- `error_code` и `error_message` — нормализованная причина неуспешного завершения.
- `started_at` и `finished_at` — фактические timestamps выполнения.
- `created_at` и `updated_at` — audit timestamps.

Default execution options:

- `max_attempts`: `3`
- `lease_seconds`: `120`
- `heartbeat_seconds`: `15`

## Index Stages

Разрешенные значения `stage` для `index_runs`:

- `queued`
- `resolving_repository`
- `cloning`
- `resolving_snapshot`
- `creating_snapshot`
- `scanning_files`
- `parsing`
- `embedding`
- `upserting_vectors`
- `publishing_artifacts`
- `finalizing`
- `completed`
- `failed`
- `canceled`
- `stale`

## Documentation Stages

Разрешенные значения `stage` для `documentation_runs`:

- `queued`
- `loading_project_model`
- `planning_sections`
- `retrieving_evidence`
- `extracting_facts`
- `generating_sections`
- `verifying_sections`
- `publishing_artifacts`
- `finalizing`
- `completed`
- `failed`
- `canceled`
- `stale`

## Error Codes

Базовый набор `error_code`:

- `unknown_error`
- `validation_failed`
- `repository_not_found`
- `repository_clone_failed`
- `repository_resolve_failed`
- `snapshot_conflict`
- `worker_lease_lost`
- `worker_heartbeat_lost`
- `timeout`
- `artifact_publish_failed`
- `embedding_failed`
- `vector_upsert_failed`
- `llm_provider_unavailable`
- `verification_failed`
- `canceled_by_user`
- `stale_lease_expired`
- `transient_infrastructure_failure`

Workers могут добавлять более точный текст в `error_message`, но UI и automation должны опираться на `error_code`.

## Code Source Of Truth

C# source of truth находится в `DopDoc.RepositoryService.Application.Jobs`:

- `JobRunStatuses`
- `JobRunStages`
- `JobRunKinds`
- `JobErrorCodes`
- `JobExecutionOptions`
- `JobExecutionContract`

Python workers должны использовать эти значения как wire contract при обновлении `index_runs` и `documentation_runs`.
