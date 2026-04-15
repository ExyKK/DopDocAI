# DopDocAI API Style Guide

## Purpose

Этот документ фиксирует единые правила для новых HTTP и SSE контрактов. Он опирается на уже существующие практики C#-сервисов проекта:

- public API идет через `EdgeGateway`;
- ошибки возвращаются как `application/problem+json` через `DopDoc.Common.Hosting`;
- auth и correlation headers уже стандартизованы в текущих C# сервисах.

Новая реализация `RepositoryService`, `ChatService`, а затем и internal contracts Python-сервисов должны придерживаться этих правил.

## Scope

Гайд применяется к:

- public REST endpoints;
- internal REST endpoints;
- SSE endpoints;
- JSON wire contracts;
- error contracts;
- headers и identity propagation.

Гайд не регулирует:

- структуру EF entities;
- внутренние Python/C# domain objects вне wire layer;
- конкретный prompt format для LLM.

## API Surface Categories

### Public endpoints

- доступны только через `EdgeGateway`;
- находятся под `/api/v1/...`;
- требуют JWT-authentication, кроме auth endpoints;
- никогда не принимают trust-sensitive identity fields от клиента.

Примеры:

- `/api/v1/auth/login`
- `/api/v1/repositories`
- `/api/v1/index-runs/{id}`
- `/api/v1/chats/{id}/messages`

### Internal endpoints

- доступны только во внутренней сети между сервисами;
- находятся под `/internal/v1/...`;
- не публикуются через gateway по умолчанию;
- могут использоваться для retrieval и worker-to-service orchestration.

Примеры:

- `/internal/v1/retrieval/search`
- `/internal/v1/documentation/templates`

### Operational endpoints

- не versioned;
- используются для liveness/readiness/diagnostics.

Примеры:

- `/health/live`
- `/health/ready`
- `/swagger`

## Path And Route Naming

- path segments пишутся в `lowercase kebab-case`;
- collection endpoints используют множественное число;
- item endpoints используют resource id в path;
- multi-word resources оформляются как `index-runs`, `documentation-runs`;
- route должен отражать domain concept, а не storage implementation.

Правильно:

- `/api/v1/repositories`
- `/api/v1/repositories/{repository_id}`
- `/api/v1/repositories/{repository_id}/snapshots`
- `/api/v1/index-runs/{index_run_id}`
- `/api/v1/documentation-runs/{documentation_run_id}`

Неправильно:

- `/api/v1/repo-index-states`
- `/api/v1/qdrant-collections`
- `/api/v1/run_index_repo`

Допустимое исключение:

- `POST /api/v1/repositories/index` допускается как входная orchestration точка для старта indexing flow по repository URL, если этот endpoint создает `index_run`.

## Versioning

- public и internal HTTP contracts versionируются в path;
- первая стабильная версия для новых сервисов — `/v1`;
- breaking changes требуют новой версии path, а не silent rewrite старой;
- non-breaking additions допускаются внутри текущей версии.

## Resource Design Rules

- использовать noun-based routes по умолчанию;
- verbs в route допустимы только для явно action-oriented orchestration endpoints;
- публичные контракты не должны раскрывать storage-specific детали;
- run lifecycle отражается как resource status, а не как набор ad-hoc route verbs.

## JSON Naming Conventions

Wire format использует `snake_case`.

Правила:

- `id` для primary identifier текущего ресурса;
- `repository_id`, `snapshot_id`, `index_run_id` для foreign/reference fields;
- timestamps заканчиваются на `_at`;
- bool fields начинаются с `is_`, `has_` или читаются как флаг состояния;
- status/stage/kind/template values — lowercase snake_case strings.

Примеры:

```json
{
  "id": "8f1f0d5b-84f2-4b7f-8dbd-6ce1c4525b2c",
  "repository_id": "bb4dcdd6-53a4-4380-9d5d-dafab2998655",
  "snapshot_id": "50853d84-f8db-4eeb-92bd-6cc4bc07a2b7",
  "status": "running",
  "stage": "embedding",
  "progress_pct": 62,
  "created_at": "2026-04-15T10:11:12Z"
}
```

## DTO Naming In Code

Для C# сервисов:

- public wire contracts размещаются в `Api/Contracts`;
- имена DTO используют суффиксы `Request`, `Response`, `Item`, `Event`;
- нельзя смешивать domain entities и wire contracts;
- JSON field names должны быть явно зафиксированы serializer policy или `JsonPropertyName`.

Рекомендуемые примеры:

- `CreateChatRequest`
- `ChatResponse`
- `IndexRunResponse`
- `IndexRunEvent`
- `SearchSourcesRequest`

Не рекомендуется:

- `ChatIn`
- `ChatOut`
- `RepoDto2`
- использование EF entity как response model.

## Headers And Identity

### Incoming public headers

- `Authorization: Bearer <token>`
- `X-Correlation-Id` optional on ingress, если клиент хочет передать свой correlation id

### Trusted internal headers

- `X-User-Id`
- `X-User-Email`
- `X-Correlation-Id`

Правила:

- `X-User-Id` и `X-User-Email` выставляются gateway;
- downstream-сервисы не принимают `user_id` из body или query;
- внешние клиенты не считаются источником истины для `X-User-Id`;
- `X-Correlation-Id` должен пробрасываться дальше между сервисами.

## Success Response Rules

### `200 OK`

Используется для синхронных read/update операций.

### `201 Created`

Используется, когда ресурс создан синхронно и уже существует как завершенная сущность.

Требования:

- вернуть body созданного ресурса;
- по возможности установить `Location`.

### `202 Accepted`

Используется для запуска долгих операций, которые выполняются асинхронно.

Требования:

- вернуть созданный `run` resource или минимальный accepted payload;
- payload обязан содержать идентификатор run и начальный status;
- клиент должен понимать, где читать status и где подписываться на SSE.

Рекомендуемый shape:

```json
{
  "id": "0f595a6a-0b5f-499a-b5ff-e9b20c14e5ff",
  "kind": "index_run",
  "status": "queued",
  "stage": "queued",
  "repository_id": "bb4dcdd6-53a4-4380-9d5d-dafab2998655",
  "snapshot_id": null,
  "status_url": "/api/v1/index-runs/0f595a6a-0b5f-499a-b5ff-e9b20c14e5ff",
  "stream_url": "/api/v1/index-runs/0f595a6a-0b5f-499a-b5ff-e9b20c14e5ff/stream"
}
```

## Error Response Rules

Новые сервисы обязаны использовать единый `ProblemDetails` contract из существующего C# foundation.

Требования:

- content type: `application/problem+json`;
- поля `title`, `status`, `type` обязательны;
- `detail` используется для человекочитаемого объяснения;
- `trace_id` и `correlation_id` должны присутствовать через common middleware;
- `error_code` должен добавляться для машинной обработки, когда ошибка доменная.

Рекомендуемый shape:

```json
{
  "type": "https://dopdoc/errors/repository-not-found",
  "title": "Repository not found",
  "status": 404,
  "detail": "Repository 50853d84-f8db-4eeb-92bd-6cc4bc07a2b7 was not found.",
  "error_code": "repository_not_found",
  "trace_id": "5f946f7e1d56f89b30dfb1c75ef6a7b2",
  "correlation_id": "d77a3b97d27446be8fc74ab76b1b3504"
}
```

Нельзя:

- возвращать ad-hoc `{ "error": "..." }`;
- терять `trace_id` на новых сервисах;
- смешивать domain error payload и exception stack trace в production ответах.

## Pagination Rules

Для публичных list endpoints использовать `limit` и `offset` в query string.

Правила:

- `limit` и `offset` — snake_case;
- значения валидируются на уровне endpoint;
- ответ возвращается в envelope, а не просто массивом.

Рекомендуемый shape:

```json
{
  "items": [],
  "limit": 50,
  "offset": 0,
  "has_more": false,
  "total_count": 0
}
```

`total_count` можно опускать только если его вычисление дорого и это явно оговорено в контракте.

## SSE Rules

SSE используется для статусов long-running jobs и streaming assistant replies.

Правила:

- content type: `text/event-stream`;
- event names используют `lowercase dot.notation`;
- каждый event несет JSON payload;
- сервис должен поддерживать `Last-Event-ID`, если endpoint заявлен как reconnect-friendly;
- периодически отправлять keepalive comments, чтобы соединение не считалось idle.

Рекомендуемые event names:

- `run.accepted`
- `run.progress`
- `run.completed`
- `run.failed`
- `chat.token`
- `chat.completed`

Рекомендуемый payload для job event:

```json
{
  "event_id": "42",
  "event_type": "run.progress",
  "run_id": "0f595a6a-0b5f-499a-b5ff-e9b20c14e5ff",
  "status": "running",
  "stage": "embedding",
  "progress_pct": 62,
  "occurred_at": "2026-04-15T10:11:12Z"
}
```

## Status Payload Rules

Все job-like ресурсы используют единый набор базовых полей:

- `id`
- `kind`
- `status`
- `stage`
- `progress_pct`
- `progress_current`
- `progress_total`
- `attempt`
- `max_attempts`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

Специфичные доменные поля добавляются поверх этого набора, но не вместо него.

## Internal Vs Public Contract Rules

### Public contract

- максимально стабильный;
- ориентирован на domain model;
- не должен раскрывать `qdrant_collection`, raw payload schema, internal storage keys.

### Internal contract

- может быть более техническим;
- может возвращать дополнительные debug fields;
- не должен становиться implicit public API через frontend или gateway.

## Backward Compatibility Policy

- новые сервисы не обязаны поддерживать legacy Python API;
- миграция фронта и compose должна идти на новые contracts;
- новые DTO и route patterns не должны подстраиваться под `repo_index_states` и другие legacy concepts.

## Recommended Service Conventions

- новые C# сервисы используют minimal APIs или однородный endpoint style в духе существующего `AuthService`;
- настройки сервиса, auth, observability, errors и health должны использовать existing common libraries;
- каждый публичный endpoint должен иметь понятный request/response contract без неявных полей.

## Examples Of Good Public Routes

- `POST /api/v1/repositories/index`
- `GET /api/v1/repositories`
- `GET /api/v1/repositories/{repository_id}`
- `GET /api/v1/repositories/{repository_id}/snapshots`
- `GET /api/v1/index-runs/{index_run_id}`
- `GET /api/v1/index-runs/{index_run_id}/stream`
- `POST /api/v1/repositories/{repository_id}/documentation-runs`
- `GET /api/v1/documentation-runs/{documentation_run_id}`
- `POST /api/v1/chats`
- `GET /api/v1/chats/{chat_id}/messages`
- `POST /api/v1/chats/{chat_id}/messages`

## Examples Of Good Internal Routes

- `POST /internal/v1/retrieval/search`
- `GET /internal/v1/snapshots/{snapshot_id}/artifacts`
- `POST /internal/v1/documentation/templates/{template_kind}/plan`

