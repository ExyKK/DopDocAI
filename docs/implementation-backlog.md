# DopDocAI Implementation Backlog

Этот backlog фиксирует целевую последовательность работ для перевода проекта в production-ready состояние с новой архитектурой:

- `AuthService` и `EdgeGateway` остаются на C#.
- `RepositoryService` и `ChatService` реализуются на C#.
- `ingestion_service` остается на Python и переписывается под worker-first indexing и новый internal retrieval contract без legacy compatibility.
- `documentation_service` реализуется на Python.
- Тяжелые процессы строятся через `Postgres-backed jobs + отдельные worker-процессы`.
- Legacy-сервисы в `backend/repos_service` и `backend/chats_service` считаются временными и не развиваются.

## Priorities

- `P0` — блокирует основную архитектуру и старт имплементации.
- `P1` — нужен для основного end-to-end use case.
- `P2` — улучшение качества, UX и эксплуатации.

## Execution Order

Работы лучше выполнять в таком порядке:

1. `ARCH-*`, `DATA-*`, `PLATFORM-*`, `CONFIG-*`
2. `REPO-*`
3. `JOBS-*`
4. `INGEST-*`, `RAG-*`
5. `CHAT-*`
6. `DOCS-*`
7. `GATEWAY-*`, `FRONT-*`
8. `OBS-*`, `TEST-*`, `OPS-*`, `LEGACY-*`

## Definition Of Done

Каждая задача считается завершенной, если:

- код вмержен в основную ветку;
- есть минимальные automated tests для измененного поведения;
- есть observability: logs + базовые metrics/traces для нового потока;
- обновлены compose/configuration и локальный сценарий запуска;
- API-контракты и payload schema зафиксированы в коде и документации.

## Epic ARCH — Architecture Freeze

### ARCH-001 — Зафиксировать service boundaries
- Priority: `P0`
- Depends on: none
- Status: `completed`
- Artifact: [Service Boundaries](./architecture/service-boundaries.md)
- Goal: формально закрепить финальный набор сервисов и зоны ответственности.
- Tasks:
- описать роли `RepositoryService`, `ChatService`, `ingestion_service`, `documentation_service`;
- зафиксировать, что `EdgeGateway` — единственная публичная точка входа;
- зафиксировать, что `user_id` больше не передается в body/query, а берется из `X-User-Id`;
- зафиксировать, что индексация и документация привязаны к `snapshot_id` и `commit_sha`.
- Acceptance:
- есть документ с service boundaries;
- все дальнейшие задачи backlog опираются на одни и те же термины: `repository`, `snapshot`, `index_run`, `documentation_run`.

### ARCH-002 — Зафиксировать API style guide
- Priority: `P0`
- Depends on: `ARCH-001`
- Status: `completed`
- Artifact: [API Style Guide](./architecture/api-style-guide.md)
- Goal: не допустить размытия контрактов между новыми сервисами.
- Tasks:
- зафиксировать naming conventions для endpoints и DTO;
- определить общие правила ответа для `202 Accepted`, ошибок, SSE, paginated list;
- определить стандарт для correlation id и user context headers;
- определить внутренние vs внешние endpoints.
- Acceptance:
- есть единый style guide для REST/SSE контрактов;
- новые сервисы используют одинаковый формат ошибок и status payload.

## Epic DATA — PostgreSQL Schema And Persistence

### DATA-001 — Создать новую схему `repo`
- Priority: `P0`
- Depends on: `ARCH-001`
- Status: `completed`
- Goal: вынести новую доменную модель репозиториев, snapshot, jobs и документации в отдельную схему.
- Tasks:
- создать проект `DopDoc.RepositoryService`;
- добавить `DbContext` и первую миграцию;
- создать таблицы `repositories`, `user_repositories`, `repository_snapshots`, `index_runs`, `index_run_events`, `analysis_artifacts`, `documentation_runs`, `documentation_sections`, `documentation_section_sources`, `documentation_artifacts`;
- создать индексы и unique constraints.
- Acceptance:
- миграция поднимается локально на чистой БД;
- схема не зависит от legacy `repos_service`.

### DATA-002 — Создать новую схему `chat`
- Priority: `P0`
- Depends on: `ARCH-001`
- Status: `completed`
- Goal: отделить chat persistence от legacy Python сервиса.
- Tasks:
- создать таблицы `chats`, `chat_messages`, `chat_message_sources`;
- поддержать привязку `chat -> repository_id + snapshot_id`;
- предусмотреть поля для usage и retrieval metadata.
- Acceptance:
- миграция поднимается локально;
- один chat может быть надежно привязан к конкретному snapshot.

### DATA-003 — Зафиксировать индексы и concurrency constraints
- Priority: `P0`
- Depends on: `DATA-001`, `DATA-002`
- Status: `completed`
- Goal: исключить дубликаты snapshot и конфликтующие активные jobs.
- Tasks:
- сделать `unique(repository_id, commit_sha)` для snapshot;
- сделать partial unique index на активный `index_run` по `repository_id`;
- сделать partial unique index на активный `documentation_run` по `repository_id + snapshot_id + template_kind`;
- добавить индексы для claim-loop jobs по `status`, `lease_until`, `created_at`.
- Acceptance:
- конкурентный запуск одинаковых работ не создает логических дублей;
- claim-loop может выбирать задачи без full scan.

### DATA-004 — Зафиксировать retention strategy
- Priority: `P1`
- Depends on: `DATA-001`
- Goal: заранее определить, что удаляется, а что хранится долго.
- Tasks:
- определить retention для `index_run_events`;
- определить политику хранения старых `documentation_runs`;
- определить soft-delete/archiving для `repositories` и `chats`;
- определить стратегию cleanup orphaned MinIO artifacts.
- Acceptance:
- есть документированная retention policy;
- схема не требует срочного рефакторинга после появления первых данных.

## Epic PLATFORM — Common .NET Foundation

### PLATFORM-001 — Подготовить solution под новые сервисы
- Priority: `P0`
- Depends on: `ARCH-001`
- Status: `completed`
- Goal: добавить в `src` новые сервисы и общие зависимости.
- Tasks:
- добавить `DopDoc.RepositoryService` и `DopDoc.ChatService` в solution;
- подключить общие проекты `DopDoc.Common.Hosting`, `DopDoc.Common.Observability`, `DopDoc.Common.Persistence`;
- настроить `appsettings`, Dockerfile, health checks и bootstrap logging.
- Acceptance:
- сервисы собираются и стартуют пустыми;
- оба сервиса видны в compose.

### PLATFORM-002 — Вынести общий user context abstraction
- Priority: `P0`
- Depends on: `PLATFORM-001`
- Status: `completed`
- Goal: унифицировать чтение `X-User-Id` и correlation headers.
- Tasks:
- создать reusable helper/abstraction для доступа к user context;
- использовать его в `RepositoryService` и `ChatService`;
- убрать потребность в `user_id` в request body/query.
- Acceptance:
- новые сервисы получают user id только из headers;
- публичные DTO не содержат `user_id`.

### PLATFORM-003 — Вынести typed clients для internal HTTP
- Priority: `P1`
- Depends on: `PLATFORM-001`
- Goal: не плодить ad-hoc HTTP вызовы между сервисами.
- Tasks:
- создать typed clients для вызовов `ingestion_service`, `documentation_service`, `RepositoryService`;
- добавить timeout, retry policy, correlation header propagation;
- покрыть клиенты contract tests.
- Acceptance:
- межсервисные HTTP вызовы типизированы и централизованы.

## Epic CONFIG — Runtime Configuration

### CONFIG-001 — Централизовать AI runtime режимы
- Priority: `P0`
- Status: `completed`
- Depends on: `RAG-004A`, `CHAT-003`, `DOCS-001`
- Artifact: [AI Runtime Configuration](./architecture/ai-runtime-config.md)
- Goal: production-like режим с real LLM/embedding должен быть дефолтом, а `stub`/`hash` — явной lightweight опцией.
- Tasks:
- ввести центральные `DOPDOC_LLM_*` и `DOPDOC_EMBEDDING_*` переменные для compose/local runtime;
- маппить `DOPDOC_*` в native env vars конкретных сервисов только внутри compose;
- переключить дефолты на `openrouter` + `deepseek/deepseek-v4-flash` и `jina_http` + `jinaai/jina-code-embeddings-0.5b`;
- сделать CUDA runtime для `embedding_service` дефолтным compose-режимом;
- обновить compose, service settings и local env templates;
- задокументировать lightweight режимы `DOPDOC_LLM_PROVIDER=stub` и `DOPDOC_EMBEDDING_PROVIDER=hash`.
- Acceptance:
- без явного stub/hash override runtime ожидает real LLM и real embedding service;
- один `.env` может управлять Chat/Docs/Ingestion AI режимом через `DOPDOC_*`;
- C# сервисы не содержат ручного чтения `DOPDOC_*` и используют стандартный configuration binding.

## Epic REPO — RepositoryService

### REPO-001 — Поднять минимальный `RepositoryService`
- Priority: `P0`
- Depends on: `DATA-001`, `PLATFORM-001`, `PLATFORM-002`
- Status: `completed`
- Goal: сервис должен стартовать, применять миграции и отдавать health/swagger.
- Tasks:
- создать setup по аналогии с AuthService;
- подключить EF Core, migrations, problem details, auth, observability;
- настроить compose/env variables.
- Acceptance:
- сервис стартует локально;
- `/health/live`, `/health/ready`, swagger и auth работают.

### REPO-002 — Реализовать CRUD модели `repository`
- Priority: `P0`
- Depends on: `REPO-001`
- Status: `completed`
- Goal: дать пользователю возможность зарегистрировать и просматривать репозитории.
- Tasks:
- реализовать `POST /repositories/index` как входную точку индексации;
- реализовать `GET /repositories`, `GET /repositories/{id}`;
- реализовать нормализацию GitHub URL;
- реализовать привязку `user_repositories`.
- Acceptance:
- пользователь может добавить публичный GitHub URL и увидеть его в списке;
- URL одного и того же репозитория не дублируется логически.

### REPO-003 — Реализовать `snapshot` lifecycle
- Priority: `P0`
- Depends on: `REPO-002`
- Status: `completed`
- Goal: RepositoryService должен знать, какой snapshot активный и какие уже существуют.
- Tasks:
- реализовать сохранение snapshot metadata;
- реализовать `GET /repositories/{id}/snapshots`;
- реализовать выбор `active_snapshot_id`;
- реализовать lookup "есть ли уже готовый snapshot для данного commit_sha".
- Acceptance:
- repository может иметь историю snapshot;
- повторная индексация того же commit не создает второй ready snapshot без необходимости.

### REPO-004 — Реализовать index/documentation run API
- Priority: `P0`
- Depends on: `REPO-003`, `JOBS-001`
- Status: `completed`
- Goal: RepositoryService становится control plane для heavy jobs.
- Tasks:
- реализовать `POST /repositories/index`;
- реализовать `GET /index-runs/{id}`;
- реализовать `POST /repositories/{id}/documentation`;
- реализовать `GET /documentation-runs/{id}`;
- реализовать DTO статусов, этапов и progress.
- Acceptance:
- API умеет создавать runs и возвращать актуальный status/progress;
- UI/clients больше не используют legacy `repo_index_states`.

### REPO-005 — Реализовать SSE status streaming
- Priority: `P1`
- Depends on: `REPO-004`
- Goal: заменить polling для индексации и документации.
- Tasks:
- реализовать `GET /index-runs/{id}/stream`;
- реализовать `GET /documentation-runs/{id}/stream`;
- стримить статус, stage, progress и последние events;
- добавить reconnect-friendly event ids.
- Acceptance:
- фронт может подписаться на прогресс без polling.

## Epic JOBS — Postgres-backed Jobs

### JOBS-001 — Спроектировать общий job execution contract
- Priority: `P0`
- Depends on: `DATA-001`
- Status: `completed`
- Artifact: [Job Execution Contract](./architecture/job-execution-contract.md)
- Goal: один и тот же execution model должен работать для index и docs jobs.
- Tasks:
- определить statuses: `queued`, `running`, `succeeded`, `failed`, `canceled`, `stale`;
- определить stages для index и docs runs;
- определить поля `worker_id`, `lease_until`, `heartbeat_at`, `attempt`, `max_attempts`;
- определить набор error codes.
- Acceptance:
- есть единый job execution contract;
- все worker-процессы используют одну и ту же модель.

### JOBS-002 — Реализовать claim loop для `index_runs`
- Priority: `P0`
- Depends on: `JOBS-001`, `REPO-004`
- Status: `completed`
- Goal: убрать heavy work из HTTP lifecycle.
- Tasks:
- реализовать SQL claim через `FOR UPDATE SKIP LOCKED`;
- реализовать lease update и heartbeat;
- реализовать safe transition `queued -> running -> succeeded/failed`;
- покрыть интеграционными тестами конкурентный claim.
- Acceptance:
- два worker-а не берут одну и ту же задачу;
- зависший job может быть переclaimed после истечения lease.

### JOBS-003 — Реализовать claim loop для `documentation_runs`
- Priority: `P1`
- Status: `completed`
- Depends on: `JOBS-001`
- Goal: переиспользовать тот же execution pattern для docs generation.
- Tasks:
- повторно использовать общий claim/lease/heartbeat infrastructure;
- реализовать docs-specific stage transitions;
- покрыть сценарии retry и stale detection.
- scaffold реализован в `documentation_service`: claim через `FOR UPDATE SKIP LOCKED`, heartbeat/lease, reclaim expired running jobs и перевод exhausted expired jobs в `stale`.
- Acceptance:
- docs jobs живут по той же модели, что и index jobs.

### JOBS-004 — Реализовать stale job recovery
- Priority: `P1`
- Depends on: `JOBS-002`
- Goal: корректно восстанавливать jobs после падения worker-а.
- Tasks:
- реализовать reaper-процесс или background sweep;
- переводить stale runs обратно в `queued` либо в `failed` при превышении лимита попыток;
- логировать recovery в `index_run_events`/`documentation_run_events`.
- Acceptance:
- убитый worker не оставляет job навсегда в `running`.

### JOBS-005 — Реализовать cancel semantics
- Priority: `P2`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: уметь прерывать долгие процессы без ручного вмешательства в БД.
- Tasks:
- добавить `cancel_requested_at`, `canceled_at`, `cancel_reason`;
- дать worker-у возможность корректно завершать run;
- реализовать endpoint отмены.
- Acceptance:
- пользователь или администратор может отменить index/doc run штатно.

## Epic INGEST — Indexing Worker And Project Analysis

### INGEST-001 — Перевести `ingestion_service` на worker-first режим
- Priority: `P0`
- Depends on: `JOBS-002`
- Status: `completed`
- Goal: текущий `BackgroundTasks` должен исчезнуть.
- Tasks:
- убрать зависимость от текущей схемы запуска через FastAPI request lifecycle;
- добавить worker entrypoint;
- не сохранять legacy ingestion/retrieval API ради совместимости;
- подготовить место под новый internal retrieval contract, который будет реализован в `RAG-*`;
- настроить compose на worker container или отдельный worker command для текущего образа.
- Acceptance:
- индексация больше не выполняется внутри HTTP запроса;
- worker можно запустить отдельно;
- новые потоки не зависят от старых `/ingest` и `/rag` контрактов.

### INGEST-002 — Реализовать clone + snapshot resolution pipeline
- Priority: `P0`
- Depends on: `INGEST-001`, `REPO-003`
- Status: `completed`
- Goal: worker должен получать конкретный commit и собирать воспроизводимый snapshot.
- Tasks:
- clone заданного репозитория;
- resolve `selected_branch` в head commit;
- checkout конкретного `commit_sha`;
- вычислить `tree_hash`, counters и metadata;
- записать snapshot в Postgres до начала тяжелого анализа.
- Acceptance:
- у каждого index_run есть точный `snapshot_id` и `commit_sha`;
- повторный запуск на том же commit может быть идемпотентным.

### INGEST-003 — Реализовать `file_inventory.json`
- Priority: `P0`
- Depends on: `INGEST-002`
- Status: `completed`
- Goal: создать детерминированный инвентарь файлов как базовый артефакт.
- Tasks:
- пройти по дереву репозитория;
- классифицировать файлы: go, markdown, config, test, binary, generated, vendor;
- вычислить `sha256`, lines count, size;
- записать артефакт в MinIO и зарегистрировать metadata в `analysis_artifacts` через internal endpoint `RepositoryService`.
- Acceptance:
- `file_inventory.json` существует для каждого успешного snapshot;
- downstream pipeline может использовать его как источник правды по файлам.

### INGEST-004 — Реализовать `go_symbols.json`
- Priority: `P0`
- Depends on: `INGEST-003`
- Status: `completed`
- Goal: получить структурированный список сущностей Go.
- Tasks:
- доработать tree-sitter extractor под функции, методы, struct, interface, type;
- извлечь package, imports, comments, signature;
- вычислить symbol ids;
- привязать symbol к file_path и line range.
- Acceptance:
- для Go файлов формируется детерминированный symbols inventory;
- symbol list пригоден и для retrieval, и для docs.

### INGEST-005 — Реализовать `package_graph.json`
- Priority: `P1`
- Depends on: `INGEST-004`
- Status: `completed`
- Goal: отразить связи пакетов внутри репозитория.
- Tasks:
- агрегировать imports по packages;
- учитывать `go.mod` и локальные import path;
- определить entrypoint packages типа `cmd/*`;
- сформировать `packages[]` и `edges[]`.
- Acceptance:
- можно восстановить package map и import graph проекта.

### INGEST-006 — Реализовать `config_inventory.json`
- Priority: `P1`
- Depends on: `INGEST-004`
- Status: `completed`
- Goal: собрать конфигурационные точки проекта.
- Tasks:
- эвристически извлечь `os.Getenv`, `flag.*`, yaml/json/toml keys, config structs;
- связать config keys с source files и symbols;
- поддержать default values и required flags, если они обнаружимы.
- Acceptance:
- handbook и `configuration_and_ops` могут строиться на основе артефакта, а не только свободного RAG.

### INGEST-007 — Реализовать `project_model.json`
- Priority: `P0`
- Depends on: `INGEST-004`, `INGEST-005`, `INGEST-006`
- Status: `completed`
- Goal: получить единую нормализованную модель проекта.
- Tasks:
- агрегировать files, packages, symbols, entrypoints, config, external integrations;
- выделить `http_surface`, если она уверенно обнаруживается;
- сформировать summary counts и topology;
- записать artifact versioned schema.
- Acceptance:
- docs generator может стартовать только по `project_model + artifacts`, без повторного глубокого анализа repo tree.

### INGEST-008 — Реализовать `commit_log.json`
- Priority: `P1`
- Depends on: `INGEST-002`
- Status: `completed`
- Goal: поддержать diff-aware документацию и историю snapshot.
- Tasks:
- собрать N последних commit;
- если есть `base_snapshot_id`, собрать интервал между base и head;
- агрегировать touched files/packages;
- записать structured commit log.
- Acceptance:
- сервис документации может строить `changes_since_previous_snapshot`.

### INGEST-009 — Укрепить artifact publishing в MinIO
- Priority: `P0`
- Depends on: `INGEST-003`..`INGEST-008`
- Status: `completed`
- Goal: все промежуточные артефакты должны строиться, публиковаться и регистрироваться единообразно.
- Current state:
- общий worker-level build/publish path вынесен в `app.worker.artifact_pipeline`;
- `file_inventory`, `go_symbols`, `package_graph`, `config_inventory`, `project_model` и `commit_log` используют единый publish/register loop;
- object key convention вынесен в общий helper `analysis_artifact_storage_key`;
- publish loop публикует checksum, content type, size и schema metadata через `RepositoryService`;
- upload/register failure paths покрыты минимальными automated tests.
- Tasks:
- расширять artifact pipeline новыми builders без разрастания `index_worker`;
- реализовать naming convention для object keys;
- публиковать checksum, content type, size;
- записывать metadata в `analysis_artifacts` через `RepositoryService`;
- делать overwrite/idempotent publish для одного snapshot;
- покрыть failure paths upload/register минимальными automated tests.
- Acceptance:
- все analysis artifacts доступны по snapshot и version.

### INGEST-010 — Передавать base snapshot context в `commit_log.json`
- Priority: `P1`
- Depends on: `INGEST-008`, `REPO-003`
- Status: `completed`
- Goal: сделать `commit_log.json` пригодным для реального diff-aware docs flow, а не только для recent-history режима.
- Tasks:
- определить предыдущий snapshot для repository/branch перед сборкой артефактов;
- передавать `base_snapshot_id` и `base_commit_sha` в `snapshot_metadata`;
- строить `base_commit_sha..HEAD`, если base commit reachable;
- явно фиксировать fallback reason, если base snapshot отсутствует или commit недостижим.
- Acceptance:
- повторная индексация нового commit формирует `commit_log.range.mode = base_to_head`;
- docs generator может строить `changes_since_previous_snapshot` без ручного поиска base snapshot.

### INGEST-011 — Укрепить compose runtime для artifact publishing
- Priority: `P1`
- Depends on: `INGEST-009`
- Status: `completed`
- Goal: сделать ручной и локальный запуск artifact pipeline предсказуемым.
- Tasks:
- добавить `ingestion_worker` dependency от `minio` healthcheck и `minio_init`;
- убедиться, что bucket существует до первой публикации артефактов;
- документировать ручной smoke path: index run -> `analysis_artifacts` rows -> MinIO objects;
- при необходимости добавить retries вокруг transient object-storage startup errors.
- Acceptance:
- свежий `docker compose up` не падает на публикации артефактов из-за неготового MinIO/bucket.

### INGEST-012 — Поддержать Go multi-module repos в `package_graph.json`
- Priority: `P0`
- Depends on: `INGEST-005`
- Status: `completed`
- Goal: корректно строить package graph для monorepo и репозиториев с несколькими `go.mod`.
- Tasks:
- находить все `go.mod` в tracked tree;
- назначать каждому Go file ближайший module root;
- формировать package ids/import paths с учетом module root;
- резолвить internal edges внутри каждого module и между локальными modules;
- отражать module metadata в `package_graph.modules[]`, не ломая root-module сценарий.
- Acceptance:
- multi-module Go repo получает корректные packages/edges/entrypoints;
- single-module репозитории сохраняют прежнюю форму данных или совместимый schema-v2 migration path.

### INGEST-013 — Улучшить `http_surface` detection
- Priority: `P1`
- Depends on: `INGEST-007`
- Status: `completed`
- Goal: повысить качество секций документации про API surface без перехода к свободному RAG.
- Tasks:
- извлекать routes из многострочных вызовов и route groups;
- поддержать типичные паттерны `chi`, `gin`, `echo`, `fiber`, `gorilla/mux`, `net/http`;
- связывать route с package, symbol/function handler, file/line;
- фиксировать confidence и unsupported patterns в structured form.
- Acceptance:
- `project_model.http_surface` уверенно описывает типичные Go HTTP services и пригоден для docs секций.

### INGEST-014 — Отделить generated docs и API specs от config inventory
- Priority: `P0`
- Depends on: `INGEST-003`, `INGEST-006`
- Status: `completed`
- Goal: не раздувать `config_inventory.json` swagger/openapi/generated artifacts и не смешивать API specs с runtime config.
- Tasks:
- расширить file classification для `swagger.json/yaml`, `openapi.json/yaml`, `api-docs`, `docs/swagger`, generated docs;
- определять OpenAPI/Swagger по content hints: top-level `openapi`, `swagger`, `paths`, `components`, `definitions`;
- исключить API specs/generated docs из `config_inventory.config_files`;
- добавить отдельный summary/classification для найденных API specs без полной раскладки всех keys;
- добавить caps: max config file bytes, max parsed keys per file, max nesting depth, explicit `truncated` metadata.
- Acceptance:
- generated swagger/openapi файлы не превращаются в тысячи config keys;
- реальные config files продолжают попадать в `config_inventory`;
- downstream может понять, что API spec найден, не загружая его целиком в LLM context.

### INGEST-015 — Сжать `project_model.json` до LLM-friendly summary model
- Priority: `P0`
- Depends on: `INGEST-007`, `INGEST-014`
- Status: `completed`
- Goal: `project_model` должен быть compact overview artifact, а не дублировать все подробные inventories.
- Tasks:
- спроектировать совместимый schema-v2 или explicit compact view для `project_model`;
- убрать из `project_model` полные списки symbols/config keys, оставив counts, top-level summaries, entrypoints, important packages, `http_surface`, integrations и source artifact refs;
- добавить budget metadata: estimated tokens/bytes, omitted sections, truncation reasons;
- оставить детальные данные в source artifacts (`go_symbols`, `package_graph`, `config_inventory`, `commit_log`);
- обновить tests на размер и отсутствие полного дублирования больших inventories.
- Acceptance:
- `project_model` для средних repo остается компактным и пригодным как стартовый context для planning;
- docs generator использует `project_model` как оглавление/manifest, а не как полный источник всех фактов.

### INGEST-016 — Добавить language-neutral monorepo workspace model
- Priority: `P0`
- Depends on: `INGEST-003`, `INGEST-005`, `INGEST-015`
- Status: `completed`
- Goal: корректно описывать monorepo и multi-language repositories без написания tree-sitter парсера под каждый язык.
- Tasks:
- выделить workspace units/apps/packages по manifests и lockfiles: `go.mod`, `package.json`, `pnpm-workspace.yaml`, `yarn.lock`, `package-lock.json`, `vite/next/nuxt/svelte/angular` hints, `Dockerfile`, compose, Makefile;
- классифицировать file ownership: backend/frontend/shared/docs/infra/generated/vendor/test;
- строить language/framework summary по extensions, manifests, imports/dependencies и key files;
- связать Go packages с workspace unit, а non-Go units описывать manifest-level metadata без AST parsing;
- добавить frontend-specific hints: route directories/pages, component directories, API client/generated SDK directories, build/test scripts;
- отразить model в `project_model.workspace_units[]` или отдельном `workspace_model.json`.
- Acceptance:
- repo с Go backend + JS/TS frontend описывается как несколько workspace units;
- documentation planner может выбрать backend/frontend/infra sections без глубокого парсинга каждого языка;
- отсутствие parser-а для языка не блокирует useful summary и retrieval indexing.

### INGEST-017 — Разделить runtime, test, generated и docs source scopes в analysis artifacts
- Priority: `P0`
- Depends on: `INGEST-015`, `INGEST-016`
- Status: `completed`
- Goal: убрать шум из planning artifacts, который стал виден на реальных репозиториях `spf13/cobra` и `DopDopTeam/image-board`.
- Tasks:
- ввести единый `source_scope`/`runtime_scope` для файлов, symbols, packages, config findings и HTTP findings: `runtime`, `test`, `generated`, `docs`, `infra`, `vendor`;
- не смешивать `_test.go`, test fixtures и generated docs с runtime summaries;
- ранжировать `project_model.code_outline.important_symbols` сначала по runtime/exported symbols, а тестовые symbols держать отдельно или сильно понижать;
- разделить package counters/imports на runtime/test/generated, чтобы `doc_test` и test-only imports не выглядели как основные package dependencies;
- сохранять ссылки на test/generated artifacts для retrieval, но не использовать их как primary planning context.
- Acceptance:
- `cobra` не получает test-heavy `important_symbols` и test flags как runtime config;
- package summaries явно показывают runtime/test/generated counts;
- docs planner может отличить production API/code от tests и generated support files.

### INGEST-018 — Уточнить extraction env/flag/config keys в Go коде
- Priority: `P0`
- Depends on: `INGEST-006`, `INGEST-017`
- Status: `completed`
- Goal: убрать false positives вроде dynamic env expressions и одновременно сохранить полезные runtime config hints.
- Tasks:
- считать high-confidence env/flag key только из string literals или надежно inferred wrapper calls;
- dynamic expressions вроде `activeHelpEnvVar(cmd.Root().Name())`, `configEnvVar(...)` и параметров helper functions сохранять как `dynamic_env_reference`, а не как конкретный key;
- поддержать простые wrappers, где literal key передается в функцию чтения env/config, например `getEnv("PORT", defaultValue)`;
- добавить confidence/source expression metadata для env/flag findings;
- dedupe findings по workspace unit, service/package и source scope.
- Acceptance:
- `cobra` не содержит env keys, составленных из expression text;
- `image-board` не содержит ложный key `key` из helper parameter `getEnv(key, ...)`;
- реальные literal env/flag keys продолжают попадать в `config_inventory`.

### INGEST-019 — Отделить DTO/API models от runtime config structs
- Priority: `P0`
- Depends on: `INGEST-006`, `INGEST-014`, `INGEST-017`
- Status: `completed`
- Goal: не считать request/response DTO, claims и persistence models runtime-конфигурацией приложения.
- Tasks:
- классифицировать structs по path/name/tags/import context как `runtime_config`, `api_contract`, `persistence_model`, `auth_claims`, `unknown`;
- считать `json`, `binding`, `gorm`, `bson`, `swagger` tags сигналами data contract, а не runtime config сами по себе;
- считать runtime config только по сильным hints: `env`, `mapstructure`, `envconfig`, `default`, `required` рядом с config/env packages или config paths;
- перенести compact summary API/data models в отдельный раздел `project_model.data_contracts` или source artifact refs, не раздувая `config_inventory`;
- обновить downstream summaries так, чтобы `required` в DTO не превращался в required runtime setting.
- Acceptance:
- `image-board` не показывает `Claims`, `LoginRequest`, `Board`, `PostDTO` и похожие DTO как runtime config structs;
- runtime config counts заметно уменьшаются без потери API/data model discoverability;
- docs generator может отдельно описывать configuration и API contracts.

### INGEST-020 — Заменить ad-hoc YAML/config flattening и отдельно обрабатывать lockfiles
- Priority: `P0`
- Depends on: `INGEST-014`, `INGEST-017`
- Status: `completed`
- Goal: сделать config inventory точнее на GitHub workflows, Dependabot, Swagger YAML и JS lockfiles.
- Tasks:
- перейти на structured YAML parsing или array-aware flattening для `*.yml/*.yaml`;
- корректно представлять массивы и повторяющиеся keys без collapse в один путь вроде `updates.directory`;
- исправить OpenAPI/Swagger YAML summary через `info`-scoped parsing, чтобы `title` не брался из вложенного `description`;
- классифицировать `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `go.sum` как dependency lock artifacts, а не runtime config files;
- дать lockfiles compact dependency summary или только metadata refs, без раскладки тысяч keys.
- Acceptance:
- `.github/labeler.yml` и похожие YAML файлы не дают пустой или разрушенный key summary;
- Dependabot arrays сохраняются различимо;
- `frontend/package-lock.json` не попадает в runtime `config_inventory.config_files`;
- Swagger YAML title extraction стабилен на `image-board`.

### INGEST-021 — Сжать `project_model` v2.1 и уточнить workspace ownership
- Priority: `P0`
- Status: `completed`
- Depends on: `INGEST-015`, `INGEST-016`, `INGEST-017`
- Goal: удержать `project_model` в разумном LLM planning budget на средних monorepo.
- Tasks:
- убрать дублирование `go.important_packages` между top-level summary и `workspace_units[].go`, оставив refs/counts/top N per unit;
- ограничить per-workspace summaries: top packages/routes/scripts/components, counts и artifact refs вместо повторения подробных payloads;
- добавить regression budget tests по bytes/estimated tokens на fixture уровня `image-board`;
- улучшить ownership для docs/site/static/assets units, а не отдавать их backend root unit по умолчанию;
- расширить infra/database ownership hints для `.gitlab-ci.yml`, `*stack.yml`, `infrastructure/**`, SQL migrations/seeds и compose files;
- расширить frontend API client hints на `services`, `http`, `api`, `client`, `clients`, generated SDK paths;
- связать `api_specs` с `workspace_unit_id`/service, когда spec явно лежит внутри service docs.
- Acceptance:
- `project_model` для `image-board` становится существенно меньше и не дублирует package summaries;
- workspace units лучше отражают backend/frontend/infra/docs/database границы;
- frontend service/http directories распознаются как API-client hints.

### INGEST-022 — Укрепить HTTP route extraction against non-router method calls
- Priority: `P0`
- Status: `completed`
- Depends on: `INGEST-013`, `INGEST-016`, `INGEST-017`
- Goal: убрать ложные routes из обычных method calls вроде `Header.Get`, `gin.Context.Get` и context helpers.
- Tasks:
- отслеживать router/group variables и разрешать route methods только на известных router receivers или route group receivers;
- валидировать path candidates: route-like literal paths, known framework wildcards и confidence для нестандартных cases;
- игнорировать `c.Get(...)`, `r.Header.Get(...)`, `Request.Context()` и похожие non-router вызовы;
- сохранять ignored candidates/diagnostics для отладки extraction без загрязнения `http_surface.routes`;
- продолжить связывать routes с package, handler, source file и `workspace_unit_id`.
- Acceptance:
- `image-board` не содержит routes `Authorization`, `X-User-Name`, `X-User-Role` и похожих header/context keys;
- реальные Gin/Chi/Echo/Fiber/Gorilla/net-http routes остаются в `http_surface`;
- unsupported patterns относятся к route registration, а не к произвольным method calls.

### INGEST-023 — Повысить signal/noise `commit_log` для merge-heavy histories
- Priority: `P1`
- Depends on: `INGEST-010`, `INGEST-016`
- Goal: сделать `commit_log.json` полезнее для будущей diff-aware документации на репозиториях с большим числом merge commits.
- Tasks:
- отделить merge commits от ordinary commits в summary и counters;
- добавить first-parent/merge-aware view или compact merge summary, чтобы пустые `touched_files` не доминировали в recent history;
- связывать touched files/packages с `workspace_unit_id`, когда ownership уже известен;
- ограничить message/body snippets и выделить themes по workspace units/package paths;
- явно фиксировать commits без file stats и причину: merge, shallow history, unreachable diff, parsing limit.
- Acceptance:
- merge-heavy history вроде `image-board` не выглядит как набор пустых изменений;
- docs generator получает compact themes по backend/frontend/infra/docs units;
- `commit_log` остается deterministic и bounded по размеру.

## Epic RAG — Vector Index And Retrieval

### RAG-001 — Выбрать модель хранения в Qdrant
- Priority: `P0`
- Status: `completed`
- Depends on: `INGEST-002`, `INGEST-016`, `INGEST-017`, `INGEST-021`
- Goal: перейти от коллекции на repo к коллекции на schema/version.
- Tasks:
- создать дизайн `code_chunks_v1`;
- определить payload поля: `snapshot_id`, `repository_id`, `commit_sha`, `file_path`, `language`, `workspace_unit_id`, `package`, `kind`, `name`, `start_line`, `end_line`, `chunk_kind`, `is_test`;
- определить payload indexes.
- Acceptance:
- retrieval возможен через filter по `snapshot_id`;
- Qdrant не просачивается в публичную доменную модель.

### RAG-002 — Реализовать chunking и deterministic chunk ids
- Priority: `P0`
- Status: `completed`
- Depends on: `RAG-001`, `INGEST-004`
- Goal: обеспечить идемпотентность и предсказуемость индекса.
- Tasks:
- определить стратегию chunking для Go entities и plain text fallback;
- формировать chunk id из `snapshot_id + file_path + symbol signature + chunk_index`;
- хранить связь `symbol -> chunk`.
- Acceptance:
- повторный индекс одного snapshot не плодит новые логические чанки.

### RAG-003 — Реализовать upsert/delete by snapshot
- Priority: `P0`
- Status: `completed`
- Depends on: `RAG-002`
- Goal: безопасно переиндексировать snapshot без мусора.
- Tasks:
- удалить старые points данного `snapshot_id` перед полной перезаливкой;
- делать batch upsert;
- логировать counters в `index_runs`.
- Acceptance:
- stale chunks не остаются после реиндексации того же snapshot.

### RAG-004A — Вынести embedding model в отдельный контейнер
- Priority: `P0`
- Status: `completed`
- Depends on: `RAG-003`
- Goal: использовать настоящие code embeddings для retrieval, не утяжеляя `ingestion_worker` и сохраняя быстрый dev/smoke режим.
- Tasks:
- ввести `EmbeddingProvider` abstraction для indexing и retrieval query embeddings;
- добавить provider modes: `hash` для lightweight dev и `jina_http` для реальной модели;
- поднять отдельный `embedding_service` container с `jinaai/jina-code-embeddings-0.5b`;
- использовать 896-dimensional vectors, совместимые с текущим `code_chunks_v1`;
- поддержать batch embedding chunks и query embedding;
- применять task prefixes для `nl2code`/technical QA: разные prefixes для query и document chunks;
- добавить health/retry/timeout handling для embedding provider;
- записывать `embedding_provider`, `embedding_model`, `embedding_dimension` и batch counters в `index_runs.StatsJson`;
- документировать ручной режим: lightweight compose без модели и quality compose с embedding container.
- Acceptance:
- lightweight smoke compose может индексировать без скачивания/загрузки модели через explicit `hash`;
- default quality compose запускает real embedding container и индексирует `code_chunks_v1` через `jina-code-embeddings-0.5b`;
- `torch/transformers` и model weights не попадают в образ `ingestion_worker`;
- повторная индексация snapshot сохраняет deterministic chunk ids и заменяет vectors без stale points;
- `RAG-004` retrieval API использует тот же provider abstraction для query vectors.

### RAG-004B — Добавить CUDA runtime для `embedding_service`
- Priority: `P1`
- Status: `completed`
- Depends on: `RAG-004A`
- Goal: сделать real embedding mode практически пригодным для локального NVIDIA dev-стенда без утяжеления `ingestion_worker`.
- Tasks:
- добавить `Dockerfile` для `embedding_service` на CUDA/PyTorch runtime;
- сделать CUDA Dockerfile дефолтным compose runtime для `embedding_service`;
- оставить lightweight `hash` mode без изменений;
- отключить шумные uvicorn access logs по умолчанию и увеличить healthcheck interval;
- снизить CUDA memory footprint для GTX 1650: conservative batch, fp16, max sequence length and allocator hint;
- добавить graceful CUDA OOM retry with smaller internal batch sizes;
- добавить ручной GPU setup guide для Arch/Omarchy + `linux-g14` + GTX 1650.
- Acceptance:
- CUDA mode использует тот же compose service name `embedding_service` и тот же `jina_http` provider contract;
- CPU/GPU embedding runtimes не меняют код retrieval/indexing;
- `/health` показывает runtime device для быстрой проверки CUDA;
- OOM на большом request не валит сервис без попытки уменьшить batch size;
- документация содержит команды настройки драйвера, NVIDIA Container Toolkit, compose запуска и проверки `nvidia-smi`.

### RAG-004C — Refactor `embedding_service` application structure
- Priority: `P1`
- Status: `completed`
- Depends on: `RAG-004B`
- Goal: убрать прототипное состояние, где serving/runtime/DTO/error handling живут в `main.py`.
- Tasks:
- вынести FastAPI route wiring в `app/api.py`;
- вынести request/response модели в `app/schemas.py`;
- вынести model loading, dtype handling, max sequence length, CUDA OOM retry и vector dimension validation в `app/runtime.py`;
- оставить `app/main.py` только ASGI entrypoint и uvicorn runner;
- сериализовать `model.encode` через lock, чтобы параллельные requests не устраивали лишний CUDA OOM;
- добавить unit tests на runtime без загрузки настоящей embedding model.
- Acceptance:
- `main.py` больше не содержит business/runtime logic;
- CUDA OOM retry и dimension validation покрыты быстрыми тестами;
- внешний HTTP contract `GET /health` и `POST /internal/embeddings` сохранён.

### RAG-004 — Реализовать retrieval API по `snapshot_id`
- Priority: `P0`
- Status: `completed`
- Depends on: `RAG-003`, `RAG-004A`, `RAG-004C`
- Goal: chats и docs не должны знать про коллекции и qdrant payload details.
- Tasks:
- реализовать внутренний endpoint `POST /internal/v1/retrieval/search`;
- принимать `snapshot_id`, `query`, `top_k`, optional filters;
- возвращать normalized source DTO;
- добавить latency metrics.
- Acceptance:
- любой downstream consumer делает retrieval только через `snapshot_id`.

### RAG-005 — Добавить hybrid retrieval
- Priority: `P1`
- Status: `completed`
- Depends on: `RAG-004`, `INGEST-007`
- Goal: улучшить точность ответов и документации.
- Tasks:
- добавить exact/path/symbol boost поверх dense search;
- использовать payload metadata из `project_model`/`go_symbols`/`package_graph` для query expansion и rerank;
- добавить rerank heuristic без отдельного ML reranker;
- сделать hybrid консервативным для общих вопросов: без `scope_boost`, без lexical boost при отсутствии явных path/symbol hints, с поддержкой русскоязычных запросов вокруг code hints.
- Acceptance:
- вопросы по символам, пакетам и конкретным файлам отвечаются стабильнее, а общие вопросы по репозиторию остаются dense-first.

### RAG-006 — Добавить token-aware chunking и length-bucketed embedding
- Priority: `P1`
- Depends on: `RAG-004`, `RAG-004A`
- Goal: ускорить real embedding runs и снизить потери от `EMBED_MAX_SEQ_LENGTH` без смены модели.
- Tasks:
- добавить token-length audit/diagnostics для retrieval chunks;
- исключить низкоценные retrieval inputs вроде статических SVG/assets и mock/sample data;
- дробить overlong chunks на token-aware windows с overlap вместо грубой line-based нарезки;
- группировать chunks по длине перед batch embedding, сохраняя deterministic chunk/vector alignment;
- записывать token length/truncation-risk counters в `index_runs.StatsJson`.
- Acceptance:
- `image-board`/`cobra`-class repositories индексируются быстрее при том же `jina-code-embeddings-0.5b`;
- chunks, которые превышают `EMBED_MAX_SEQ_LENGTH`, не теряют полезный хвост без явного split;
- retrieval chunk payload remains source-complete для downstream citations.

## Epic CHAT — ChatService

### CHAT-001 — Поднять минимальный `ChatService`
- Priority: `P0`
- Depends on: `DATA-002`, `PLATFORM-001`, `PLATFORM-002`
- Goal: сервис должен стартовать и владеть своей БД.
- Tasks:
- создать setup по образцу AuthService;
- подключить DbContext, auth, health, observability;
- настроить compose/env variables.
- Acceptance:
- сервис стартует локально и имеет свою схему `chat`.

### CHAT-002 — Реализовать chat CRUD
- Priority: `P0`
- Status: `completed`
- Depends on: `CHAT-001`, `REPO-003`
- Goal: создавать и читать snapshot-bound чаты.
- Tasks:
- реализовать `POST /chats`, `GET /chats`, `GET /chats/{id}`, `GET /chats/{id}/messages`;
- при создании чата принимать `repository_id` и optional `snapshot_id`;
- если `snapshot_id` не передан, выбирать последний ready snapshot;
- проверять repository/snapshot ownership через `RepositoryService` typed client;
- использовать `RepositoryService` ready snapshot lookup, чтобы chat не привязывался к snapshot без successful `index_run`.
- держать CRUD-логику отдельно от message/retrieval pipeline, чтобы создание чата не тянуло за собой prompt/LLM concerns.
- Acceptance:
- chat всегда знает, к какому snapshot относится, а public API не принимает `user_id` в body/query.

### CHAT-003 — Реализовать send message pipeline
- Priority: `P0`
- Status: `completed`
- Depends on: `CHAT-002`, `RAG-004`
- Goal: восстановить основной use case чата на новой архитектуре.
- Tasks:
- загрузить chat history;
- выполнить retrieval через `snapshot_id`;
- собрать prompt c жесткими source rules;
- вызвать LLM provider;
- сохранить `chat_messages` и `chat_message_sources`;
- поддержать `stub` dev provider и OpenAI/OpenRouter-compatible provider через конфиг.
- скрыть HTTP wire contracts RepositoryService/RetrievalService за typed clients и компактными application models.
- Acceptance:
- пользователь может задавать вопросы по snapshot и получать grounded answer с источниками через `POST /api/v1/chats/{chat_id}/messages`.

### CHAT-004 — Реализовать usage and source persistence
- Priority: `P1`
- Depends on: `CHAT-003`
- Goal: сделать chat пригодным для анализа и отладки.
- Tasks:
- сохранять `input_tokens`, `output_tokens`, `provider`, `finish_reason`;
- сохранять normalized citations и scores;
- сохранить retrieval/generation latency.
- Acceptance:
- по каждому assistant message видно, какие chunks были использованы и во что обошелся ответ.

### CHAT-005 — Реализовать streaming replies
- Priority: `P1`
- Depends on: `CHAT-003`
- Goal: улучшить UX без изменения core logic.
- Tasks:
- реализовать `POST /chats/{id}/messages/stream`;
- отправлять partial tokens и финальные normalized sources;
- обеспечить корректное завершение и сохранение финального сообщения.
- Acceptance:
- фронт может стримить ответ LLM.

## Epic DOCS — Documentation Generator

### DOCS-001 — Создать `documentation_service` scaffold
- Priority: `P0`
- Status: `completed`
- Depends on: `DATA-001`, `JOBS-003`
- Goal: поднять отдельный Python сервис/worker для генерации документации.
- Tasks:
- создать структуру проекта и docker image;
- реализовать worker entrypoint для `documentation_runs`;
- подключить Postgres, MinIO, observability.
- scaffold был расширен в `DOCS-002`/`DOCS-003`: worker теперь создает section plan и sources, а генерация текста/артефактов начинается в `DOCS-004`.
- Acceptance:
- сервис стартует и может claim-ить jobs.

### DOCS-002 — Реализовать section planning
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-001`, `INGEST-007`
- Goal: генератор должен строить документацию не “целиком одним промптом”, а по схеме разделов.
- Tasks:
- определить template schema для `developer_handbook`;
- создать section plan с fixed section keys;
- записывать sections в `documentation_sections`.
- реализован fixed `developer_handbook` plan из 10 разделов и internal RepositoryService endpoint для атомарной замены section plan.
- Acceptance:
- один `documentation_run` создаёт предсказуемый набор sections.

### DOCS-003 — Реализовать evidence retrieval per section
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-002`, `RAG-004`
- Goal: каждый раздел должен опираться на structured artifacts и search.
- Tasks:
- читать `project_model`, `package_graph`, `config_inventory`, `commit_log`;
- при необходимости делать retrieval по `snapshot_id`;
- формировать normalized section evidence pack;
- сохранять section sources.
- `documentation_worker` загружает analysis artifacts из MinIO, строит normalized evidence per section, добавляет structured artifact/file sources и optional retrieval sources.
- Acceptance:
- секции документации имеют machine-readable source set.

### DOCS-004 — Реализовать `developer_handbook`
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-003`
- Goal: получить первый реально полезный тип документации.
- Tasks:
- сгенерировать sections `overview`, `repository_layout`, `package_map`, `entry_points`, `major_flows`, `domain_entities`, `integrations`, `configuration`, `build_run_test`, `known_gaps`;
- собрать `documentation.md` и `manifest.json`;
- сохранить section artifacts и bundle.
- реализован deterministic evidence-based generator: worker публикует section markdown, общий `documentation.md`, `manifest.schema-v1.json` в MinIO и регистрирует metadata в `repo.documentation_artifacts`.
- Acceptance:
- можно сгенерировать developer handbook для проиндексированного snapshot.

### DOCS-005 — Реализовать `api_reference`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-007`
- Goal: генерировать API reference, если проект действительно содержит HTTP surface.
- Tasks:
- использовать `http_surface` из `project_model`;
- генерировать summary и endpoint sections;
- помечать документ partial, если источников недостаточно.
- Acceptance:
- при наличии API в репозитории можно получить пригодную reference doc.

### DOCS-006 — Реализовать `configuration_and_ops`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-006`
- Goal: выдавать полезную документацию по конфигурации и эксплуатации.
- Tasks:
- использовать `config_inventory` и related source files;
- описать env vars, config files, external services, локальный запуск;
- собирать dedicated artifact bundle.
- Acceptance:
- документ отражает найденные настройки и зависимости проекта.

### DOCS-007 — Реализовать `changes_since_previous_snapshot`
- Priority: `P1`
- Depends on: `DOCS-003`, `INGEST-008`
- Goal: поддержать changelog-style документацию между snapshot.
- Tasks:
- использовать `base_snapshot_id`;
- агрегировать commits, changed packages, possible impact;
- формировать diff-based documentation artifact.
- Acceptance:
- по двум snapshot можно получить readable change summary с источниками.

### DOCS-008 — Реализовать LLM-assisted verification pipeline
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-012`, `DOCS-017`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: документация должна проходить серьёзную проверку качества, groundedness и полезности before successful completion.
- Tasks:
- добавить deterministic preflight: manifest v2 integrity, documents/sections/artifacts consistency, unknown citations, empty sections, unfinished markdown/code fences, raw JSON dumps;
- добавить configurable verification mode: `deterministic`, `llm`, `hybrid`, где production-like режим использует `hybrid`;
- определить structured LLM judge contract с JSON response schema для section-level и document-set-level verdicts;
- для каждой секции проверять groundedness claims against rendered evidence/source ids: `supported`, `partially_supported`, `unsupported`, `contradicted`, `not_enough_evidence`;
- проверять section usefulness against `section_spec`: coverage of `must_cover`, соблюдение `avoid`, actionable details, отсутствие inventory-пересказа;
- проверить cross-document quality: brief не перегружен reference details, onboarding содержит практические шаги, architecture/reference/change_report не смешивают intent;
- отдельно проверять commit-history safety: SHA/commit-derived claims должны жить в `change_report`, а historical deletion не должен превращаться в current-state claim без evidence;
- сохранять `verification_report.schema-v1.json` с deterministic findings, LLM judge verdicts, scores, severities, evidence references и suggested fixes;
- добавлять `verification_summary` в run summary/manifest; hard errors fail run, warnings mark run as succeeded with degraded verification status.
- Acceptance:
- каждый successful docs run имеет verification report и machine-readable summary;
- unsupported/contradicted technical claims по files/APIs/commands/config приводят к failed run;
- weak usefulness, duplication или missing `must_cover` приводят к warnings/degraded status, а не молча проходят;
- LLM judge output строго валидируется по schema и при невалидном ответе даёт retryable verification failure;
- verification можно запустить в deterministic-only mode для дешёвых smoke runs.
- Notes:
- реализован `DocumentationVerifier` с режимами `deterministic`, `llm`, `hybrid`; production-like default в compose/env — `hybrid`, а `stub` LLM автоматически использует deterministic-only verification для smoke runs;
- deterministic checks покрывают manifest v2, documents/sections, unknown citations, missing body citations, short sections, raw JSON dumps, unclosed code fences, `finish_reason=length` и commit-hash leakage вне `change_report`;
- LLM judge вызывается на каждую секцию и на весь document set, возвращает strict JSON findings/scores/call metadata, а невалидный JSON помечается как retryable `verification_judge_invalid_response`;
- финальный `verification_report.schema-v1.json` и `verification_summary` публикуются в MinIO/manifest/run summary; hard errors fail run после repair attempts.

### DOCS-008B — Добавить repair loop по verification findings
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-008`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: verification должна не только валить результат, но и давать системе шанс автоматически исправить repairable quality errors без полного перезапуска run.
- Tasks:
- добавить controlled loop `generate -> verify -> repair -> verify`, отдельный от технических job retries;
- строить `repair_plan.schema-v1.json` из verification findings: проблемные секции, repairable errors, required fixes, unresolved/non-repairable findings;
- перегенерировать только секции с repairable `error` findings, используя original section markdown, `section_spec`, rendered evidence, allowed source ids и relevant verification findings;
- запретить repair prompt добавлять факты вне evidence; unsupported/contradicted claims должны удаляться или заменяться honest unknown/partial statements;
- после repair пересобирать affected intent-based documents, index `documentation.md` и `manifest.schema-v2.json`;
- сохранять audit artifacts для repair rounds: `sections/{section_key}.repair-{n}.md`, `repair_attempts.schema-v1.json`, final repaired section artifact;
- ограничить loop safety guard'ом, например `max_repair_rounds=2`, и останавливать повторяющиеся unresolved findings;
- hard fail оставить только после исчерпания repair rounds или при non-repairable errors вроде missing evidence / invalid judge contract / empty evidence pack.
- Acceptance:
- unknown citations, unsupported claims, wrong-scope text и markdown defects могут быть исправлены без полной регенерации всех секций;
- final report показывает repair rounds, repaired sections и unresolved findings;
- job retry не используется для quality repair, а только для технических retryable failures;
- repair loop не может уйти в бесконечную генерацию.
- Notes:
- реализован bounded loop `generate -> verify -> repair -> verify` внутри documentation pipeline, управляется `DOPDOC_DOCS_MAX_REPAIR_ROUNDS`/`DOCS_MAX_REPAIR_ROUNDS` с default `2`;
- `repair_plan.schema-v1.json` строится из repairable `error` findings, а non-repairable errors остаются unresolved и не маскируются повторной генерацией;
- repair prompt получает original section markdown, `section_spec`, allowed source ids, source index, original prompt payload и relevant findings; пересобирается только проблемная секция;
- repair audit artifacts теперь attempt-scoped после `DOCS-022`: `attempts/{attempt}/sections/{section_key}.repair-{n}.md`, draft section markdown, draft intent-based documents и `repair_attempts.schema-v1.json`; stable final docs/manifest публикуются только при successful verification.

### DOCS-008C — Усилить verification/repair через targeted evidence expansion
- Priority: `P1`
- Depends on: `DOCS-008`, `DOCS-008B`, `RAG-005`
- Goal: repair должен уметь не только переписывать секцию по старому evidence pack, но и точечно добирать недостающие факты, когда verification finding показывает реальный evidence gap.
- Tasks:
- расширить `VerificationFinding`/LLM judge contract полями `claim`, `evidence_needed`, `repair_strategy` (`rewrite_existing`, `expand_evidence`, `remove_claim`) и optional `retrieval_hints`;
- добавить lightweight claim extraction для generated section: выделять атомарные claims по files/APIs/commands/config/current behavior, чтобы judge и repair работали не только с общим текстом секции;
- в `RepairPlan` отделять findings, где нужен новый retrieval (`missing_coverage`, `not_enough_evidence`, важный `unsupported_claim` по `must_cover`), от findings, где retrieval вреден или не нужен (`unknown citation`, `markdown hygiene`, `wrong_scope`, contradicted claims);
- строить targeted repair retrieval queries из `claim + evidence_needed + section_spec.must_cover + repository/template context` с маленьким `top_k` и фильтрами по `snapshot_id`, `workspace_unit_id`, `source_scope`, `language`, если они известны;
- публиковать `repair_evidence_delta.schema-v1.json`: какие findings запросили retrieval, какие queries были выполнены, какие новые sources добавлены или почему evidence не найден;
- расширять repair prompt новыми evidence delta sources с новыми stable source ids, не смешивая их бесследно с исходным evidence pack;
- запретить repair использовать targeted retrieval для оправдания противоречащих evidence claims: если новый evidence не подтвердил claim, claim удаляется или заменяется honest unknown/partial statement;
- добавить source-neighborhood expansion для найденных retrieval chunks: при необходимости подтягивать соседние chunks/символ/файл в пределах малого бюджета.
- Acceptance:
- missing coverage по важным `must_cover` пунктам может быть исправлен через targeted retrieval без полной регенерации всех секций;
- repair artifacts показывают, какие новые evidence sources были добавлены и какое finding они закрывали;
- unsupported/contradicted hallucinations не превращаются в "поиск оправдания": при отсутствии подтверждения они удаляются;
- повторный verification видит новые source ids как допустимые и проверяет repaired section against old + delta evidence;
- если targeted retrieval ничего не нашёл, repair остаётся честным partial/unknown, а report сохраняет unresolved finding.

### DOCS-009 — Ввести token-budgeted evidence packs
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-003`, `INGEST-015`, `INGEST-016`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: генератор документации не должен отправлять в LLM целые raw artifacts без бюджета и отбора.
- Tasks:
- определить per-section evidence budget для `developer_handbook`, `api_reference`, `configuration_and_ops`, `changes_since_previous_snapshot`;
- собирать evidence pack из compact `project_model`, targeted slices source artifacts и retrieval chunks;
- добавлять `omitted_sources`, `truncated_sources`, `estimated_tokens`, `selection_reason`;
- предпочитать structured summaries, а не полные JSON inventories;
- сохранять evidence pack manifest для отладки и verification.
- Acceptance:
- каждый section prompt имеет предсказуемый размер и source provenance;
- большие artifacts не попадают в LLM context целиком;
- verification может объяснить, какие источники были использованы или отброшены.
- Notes:
- реализовано в `documentation_service` как per-section `EvidencePack` с дефолтами `120000` total tokens, `16000` tokens per source и `80` sources, рассчитанными под выбранный DeepSeek V4 Flash 1M-context режим;
- worker публикует `evidence_packs.schema-v1.json`, а run summary включает counts и token estimates.

### DOCS-010 — Добавить LLM provider layer в `documentation_service`
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-009`, `CHAT-003`
- Artifact: [AI Runtime Configuration](./architecture/ai-runtime-config.md)
- Goal: `documentation_service` должен вызывать внешнюю LLM через конфигурируемый provider, не завязываясь на конкретный OpenRouter model id.
- Tasks:
- вынести LLM-клиент в отдельный infrastructure слой по аналогии с `ChatService`;
- поддержать `stub` dev mode и OpenAI/OpenRouter-compatible chat completions;
- добавить настройки `DOCS_LLM_PROVIDER`, `DOCS_LLM_ENDPOINT`, `DOCS_LLM_API_KEY`, `DOCS_LLM_MODEL`, `DOCS_LLM_TEMPERATURE`, `DOCS_LLM_MAX_TOKENS`, `DOCS_LLM_TIMEOUT_SECONDS`;
- передавать OpenRouter app attribution headers и предусмотреть provider routing/max price knobs;
- обрабатывать timeout/rate-limit/provider errors как retryable documentation run failures.
- Acceptance:
- documentation worker может сгенерировать одну секцию через real LLM provider или stub без изменения pipeline-кода;
- provider/model/latency/token usage сохраняются в run summary.
- Notes:
- реализован `app.infra.llm_client` с `stub`, `openai_compatible` и `openrouter`;
- OpenRouter запросы получают attribution headers, metadata, provider routing JSON и `provider.max_price` knobs;
- timeout/rate-limit/5xx ошибки помечаются retryable и могут переочередить documentation run, пока не исчерпан `MaxAttempts`.

### DOCS-011 — Спроектировать prompt contract для section generation
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-009`, `DOCS-010`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: LLM должна получать компактный, проверяемый section prompt и возвращать markdown без неподтвержденных утверждений.
- Tasks:
- определить system/developer/user prompt template для `developer_handbook`;
- передавать section plan, bounded evidence pack, source ids и explicit citation rules;
- запретить выдумывать файлы, команды, API и зависимости вне evidence;
- поддержать русский/английский output language через config или run option;
- добавить golden prompt fixtures для 2-3 типовых секций.
- Acceptance:
- prompt для каждой секции помещается в заданный token budget;
- LLM output ссылается только на предоставленные source ids;
- отсутствие evidence приводит к честному partial/unknown тексту, а не hallucination.
- Notes:
- реализован schema-versioned prompt contract manifest с `system`/`developer`/`user` messages, strict citation rules и output language `ru` по умолчанию;
- добавлены golden fixture и unit coverage; фактический LLM вызов подключён в `DOCS-010`/`DOCS-012`.

### DOCS-012 — Заменить deterministic `developer_handbook` generator на LLM-backed generation
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-010`, `DOCS-011`
- Goal: убрать deterministic prose generator из production path и генерировать полезные markdown sections через LLM.
- Tasks:
- заменить `DeveloperHandbookGenerator.generate_sections` на LLM-backed section generation;
- оставить deterministic/stub генератор только для smoke/dev режима;
- генерировать секции последовательно с progress updates и сохранением per-section errors;
- собрать общий `documentation.md` из LLM sections без повторной генерации всего документа одним промптом;
- сохранять model/provider/usage/finish_reason per section в manifest или run summary.
- Acceptance:
- manual `index -> documentation` run создаёт LLM-generated `developer_handbook`;
- deterministic markdown больше не используется при `DOCS_LLM_PROVIDER != stub`;
- failed section не теряет уже опубликованные diagnostics и переводит run в корректный failed/retryable статус.
- Notes:
- секции генерируются последовательно из prompt contracts, публикуются сразу после успешной генерации и затем собираются в общий `documentation.md`;
- manifest и run summary сохраняют provider/model/usage/finish_reason/latency per section;
- при ошибке генерации публикуется `generation_errors.schema-v1.json`, а retryable LLM ошибки возвращают run в `queued`, если попытки ещё доступны.

### DOCS-013 — Добавить LLM usage accounting и экспериментальную оценку качества
- Priority: `P1`
- Depends on: `DOCS-012`, `DOCS-008`, `DOCS-008B`
- Goal: дипломные эксперименты должны быть воспроизводимыми: по каждому run должно быть видно, сколько стоили generation/verification и какое качество получилось.
- Tasks:
- считать actual input/output tokens для generation и verification отдельно;
- считать repair round usage отдельно от первичной generation;
- считать примерную стоимость run по provider/model/pricing snapshot, без блокирующих лимитов на этом этапе;
- логировать provider/model/pricing snapshot и verification mode, чтобы результаты экспериментов можно было объяснить;
- собрать evaluation summary из `verification_report`: groundedness, usefulness, coverage, source quality, readability, duplication, wrong-scope findings;
- сохранить результаты ручных прогонов для `cobra` и `image-board` как baseline notes/table;
- добавить минимальную структуру для сравнения моделей/настроек в дипломных экспериментах.
- Acceptance:
- после запуска видно, сколько стоили generation, verification и repair по секциям/документам и всему run;
- verification summary можно использовать как baseline quality table для диплома;
- отсутствие pricing metadata не ломает run, но явно помечается как unknown cost.

### DOCS-020 — Добавить structured observability для documentation pipeline
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-012`, `DOCS-008`, `DOCS-008B`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: failed/partial documentation run должен быть диагностируемым без ручного чтения MinIO/Postgres и без догадок по `httpx` логам.
- Tasks:
- ввести structured logs для `documentation_worker` и pipeline stages с обязательными полями: `documentation_run_id`, `attempt`, `repository_id`, `snapshot_id`, `template_kind`, `effective_template_kind`, `stage`, `section_key`, `repair_round`, `llm_task`, `artifact_kind`;
- логировать template selection и repository classification: kind, confidence, top signals, selected template and reason;
- логировать LLM call lifecycle: task, provider/model, prompt token estimate, source count, response id, finish reason, actual token usage, latency, retry attempt;
- логировать artifact publication: artifact kind, storage key, schema version, size, checksum, section key;
- публиковать `pipeline_trace.schema-v1.json` с компактным ordered event log по stage/section/LLM/artifact events;
- публиковать partial diagnostic artifact при падении generation, verification или repair: failed task, section key, retryable flag, provider response metadata, last successful section, already published artifacts;
- добавить `log_level`/`trace_artifact_enabled` config knobs, но production-like local default должен оставлять trace artifact включённым.
- Acceptance:
- по одному failed run можно понять, на какой секции/judge/repair call он упал и какие артефакты относятся к этой попытке;
- логи показывают requested/effective template и почему classifier выбрал именно его;
- failed run публикует machine-readable diagnostics даже если verification не дошёл до final report;
- `pipeline_trace.schema-v1.json` не содержит полные prompt/response bodies и не раскрывает secrets.
- Notes:
- добавлен `pipeline_trace.schema-v1.json` с ordered events по stage, LLM, judge, repair и artifact publication;
- добавлен `pipeline_error.schema-v1.json` для technical failures до финального verification report;
- worker/pipeline логируют progress, template selection, LLM lifecycle и artifact publication key-value сообщениями;
- добавлены `DOPDOC_DOCS_LOG_LEVEL` и `DOPDOC_DOCS_PIPELINE_TRACE_ENABLED`, trace включён по умолчанию.

### DOCS-021 — Укрепить LLM call policy, JSON mode и retry на уровне вызова
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-010`, `DOCS-008`, `DOCS-020`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: один пустой ответ модели или битый JSON judge не должен переигрывать весь documentation run через job retry.
- Tasks:
- расширить `LlmClientConfig` и OpenAI/OpenRouter-compatible client поддержкой per-call `response_format`, включая JSON object mode для judge/structured tasks;
- для verification judge включить JSON mode по умолчанию, если provider/model supports it; для обычной генерации оставить markdown mode;
- добавить call-level retry wrapper для `section_generation`, `section_repair`, `section_judge`, `document_set_judge`: retry `llm_response_empty`, timeout, rate-limit/5xx, invalid judge JSON в пределах конкретного вызова;
- при invalid judge JSON делать retry с более жёстким correction prompt / system reminder, не запуская заново generation stage;
- после исчерпания call-level attempts публиковать `llm_call_error.schema-v1.json` или включать ошибку в `pipeline_trace`: task, section key, response id, finish reason, sanitized response excerpt, error code;
- разделить retryable technical provider failures и quality verification failures: technical failures retry locally first, quality failures идут в repair loop или final failed report;
- добавить unit tests на JSON mode request payload, empty response retry, invalid judge JSON retry и exhausted call-level failure.
- Acceptance:
- `verification_judge_invalid_response` не переводит run в job-level retry, пока не исчерпаны call-level attempts;
- `llm_response_empty` на одной секции повторяет только эту секцию, а не весь run;
- judge получает JSON-mode request, когда режим поддержан;
- при exhausted call retry run содержит diagnostic artifact с section/task context.
- Notes:
- `LlmCompletionProvider.generate` получил per-call `response_format`, OpenRouter/OpenAI-compatible request теперь умеет JSON object mode;
- judge использует JSON mode по умолчанию и retry correction message при invalid JSON;
- `call_llm_with_retry` ретраит generation, repair, section judge и document-set judge на уровне конкретного вызова;
- exhausted retries сохраняют task/section/attempt/retry metadata в exception details и diagnostic artifacts;
- добавлены тесты на JSON-mode payload, retry пустого ответа, retry invalid judge JSON и trace sanitization.

### DOCS-022 — Сделать documentation artifacts attempt-scoped и resumable
- Priority: `P1`
- Status: `completed`
- Depends on: `DOCS-020`, `DOCS-021`
- Artifact: [Documentation Evidence Packs And Prompt Contract](./architecture/documentation-prompt-contract.md)
- Goal: повторные job attempts не должны смешивать артефакты разных попыток и не должны без необходимости терять уже успешно созданные секции.
- Tasks:
- добавить attempt-aware artifact key convention, например `documentation-runs/{run_id}/attempts/{attempt}/...`, и финальные stable pointers/artifacts только после successful verification;
- включить `attempt` в metadata регистрации documentation artifacts и diagnostics;
- разделить draft artifacts (`section_markdown`, attempts, partial documents, trace) и final artifacts (`documentation.md`, intent-based docs, manifest) на уровне key convention/artifact kind;
- при job-level retry читать existing attempt state и решать, можно ли reuse уже completed sections или нужно начинать новый clean attempt;
- не перезаписывать `generation_errors.schema-v1.json`, `verification_error.schema-v1.json`, `repair_attempts.schema-v1.json` от предыдущей попытки;
- обновить cleanup/retention notes: старые attempts можно хранить для дипломных экспериментов, но final consumers должны видеть только final manifest/documentation artifacts.
- Acceptance:
- в MinIO/Postgres видно, какие artifacts принадлежат attempt 1/2/3;
- failed run не выглядит как успешная смесь секций и repair attempts из разных попыток;
- public/latest documentation consumers не получают draft artifacts;
- повторный attempt может reuse безопасные завершённые секции или явно начинает новую isolated attempt.
- Notes:
- RepositoryService теперь хранит `attempt` в `repo.documentation_artifacts`, возвращает его в artifact DTO и умеет list artifacts by documentation run/attempt;
- documentation worker публикует draft/debug artifacts под `documentation-runs/{run_id}/attempts/{attempt}/...`;
- draft reader-facing artifacts получают `draft_*` artifact kinds, а stable `documentation.md`, intent docs и `manifest.schema-v2.json` публикуются только после успешной verification;
- job-level retry читает existing artifact state и явно выбирает `clean_attempt`, фиксируя решение в `pipeline_trace`;
- добавлена EF migration `20260525000100_AddDocumentationArtifactAttempt`.

### DOCS-023 — Исправить classification и evidence scope для Go library/CLI репозиториев
- Priority: `P0`
- Depends on: `DOCS-016`, `DOCS-016B`, `DOCS-017`, `RAG-005`
- Goal: Cobra-like repositories должны получать typed Go library/CLI documentation, а retrieval evidence не должен превращать consumer docs/examples в current-state claims о самом репозитории.
- Tasks:
- поправить classifier scoring: root Go module without HTTP/frontend/API specs should be `library`/`cli_tool` even if workspace role is currently `backend`;
- добавить explicit signals for Go library packages: exported symbols, package name/module path, no runnable entrypoint package, docs package, CLI/Cobra terms;
- добавить regression test на real-ish `spf13/cobra` artifact shape: `developer_handbook` request должен auto-select `go_library_handbook`;
- пересмотреть retrieval queries/filters для Go library template: current architecture sections должны предпочитать runtime Go symbols/packages over `site/content/*` consumer docs;
- помечать docs/user-guide retrieval as `consumer_example` или lower-priority source для claims о consuming applications, чтобы модель не утверждала наличие `main.go`/`cmd.Execute()` внутри библиотеки;
- добавить prompt rule для Go library sections: distinguish repository implementation from examples showing how downstream applications use the library;
- добавить verification check/warning для wrong-scope consumer-example claims, особенно в entry points / command lifecycle sections.
- Acceptance:
- для `spf13/cobra` effective template становится `go_library_handbook`;
- generated docs не утверждают, что Cobra repository itself has `main.go`/`cmd.Execute()` entrypoint based only on `site/content/user_guide.md`;
- retrieval sources in command lifecycle/public API sections are primarily runtime symbols and package graph evidence;
- wrong-scope consumer-doc claims попадают в verification findings или repair plan.

### DOCS-019 — Добавить optional per-run caps и budget guardrails
- Priority: `P2`
- Depends on: `DOCS-013`
- Goal: позже добавить управляемые лимиты стоимости/объёма без блокировки текущего перехода к качественной генерации и verification.
- Tasks:
- добавить per-run caps: max sections, max input tokens, max output tokens, max judge calls, max estimated USD;
- добавить fail-fast preflight по estimated budget до внешних LLM calls;
- добавить настройки soft/hard cap behavior для локальных экспериментов;
- отразить budget cap hits в run summary и verification/evaluation artifacts.
- Acceptance:
- можно явно ограничить стоимость одного documentation run;
- cap violations объяснимы и не оставляют run без diagnostics.

### DOCS-014 — Добавить hygiene post-processing и source appendix
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-012`
- Goal: убрать механические дефекты LLM output и сделать citations понятными читателю.
- Tasks:
- запретить модели генерировать heading секции и нормализовать output как body-only;
- в post-process удалять ведущие `#`/`##` heading, если модель всё равно их вернула;
- добавлять к каждой секции или к концу документа source appendix с mapping `S1 -> artifact/file/chunk`;
- сделать source ids устойчивее в собранном документе: например `overview:S1` или section-local appendix рядом с секцией;
- ловить очевидные текстовые артефакты: repeated n-grams, склеенные слова, незакрытые markdown/code fences, `finish_reason=length`;
- добавить warnings в manifest/run summary, не только markdown.
- Acceptance:
- итоговый `documentation.md` не содержит двойных заголовков;
- citations можно расшифровать без обращения к Postgres/MinIO;
- секция с `finish_reason=length` или грубыми текстовыми дефектами помечается как degraded/failed для verification.
- Notes:
- `LlmSectionGenerator` нормализует body-only output, удаляет ведущие markdown headings и добавляет section-local `### Sources`;
- generation metadata теперь содержит `warnings` и `quality_status`, а run summary собирает `degraded_sections`;
- добавлены проверки на `finish_reason=length`, незакрытые code fences, склеенные повторы и repeated phrases.

### DOCS-015 — Заменить raw JSON evidence на curated evidence renderers
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-009`, `DOCS-012`
- Goal: LLM должна получать короткие, семантически подготовленные факты, а не большие JSON dumps.
- Tasks:
- сделать per-artifact renderers для `project_model`, `package_graph`, `config_inventory`, `commit_log`;
- рендерить evidence в Markdown/таблицы/списки с явными границами record'ов;
- ограничивать package/config/commit evidence top-N по релевантности к секции;
- не передавать generated Swagger chunks в общий retrieval context по умолчанию;
- для API sections использовать compact `api_specs` summaries вместо raw `docs.go`;
- сохранять и raw evidence pack, и rendered evidence pack для отладки.
- Acceptance:
- prompt contracts содержат readable rendered evidence вместо больших вложенных JSON массивов;
- generated files не загрязняют non-API sections;
- модель перестаёт путать поля соседних JSON objects в commit/config evidence.
- Notes:
- добавлен `rendered_evidence_pack_manifest` с markdown/table renderers для project/package/config/commit evidence;
- prompt contract передаёт rendered sources вместо raw nested JSON, при этом raw `evidence_pack_manifest` сохраняется для debug;
- retrieval context фильтрует generated Swagger/codegen chunks для generic handbook sections.

### DOCS-016 — Ввести repo classification и typed documentation templates
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-012`, `INGEST-017`
- Goal: документация должна подстраиваться под тип репозитория, а не всегда использовать один `developer_handbook`.
- Tasks:
- классифицировать snapshot как `library`, `cli_tool`, `backend_service`, `frontend_app`, `monorepo_web_app`, `mixed`;
- использовать признаки из `project_model`, `package_graph`, `config_inventory`: workspace units, modules, package managers, HTTP surface, frontend manifests, CLI/library signatures;
- добавить template selection для documentation run, если пользователь не указал template вручную;
- сделать `go_library_handbook` для Cobra-like repos;
- сделать `monorepo_web_app_handbook` для image-board-like repos;
- сохранить выбранный template и classification summary в run summary/manifest.
- Acceptance:
- `spf13/cobra` получает library-oriented sections: public API, command lifecycle, flags/args, completions, doc generation, testing;
- `image-board` получает monorepo-oriented sections: service map, local development, request flows, data model, API surface, frontend, deployment;
- generic `developer_handbook` остаётся fallback, а не основной путь для всех репозиториев.
- Notes:
- добавлен artifact-driven classifier с kinds `library`, `cli_tool`, `backend_service`, `frontend_app`, `monorepo_web_app`, `mixed`;
- default/requested `developer_handbook` теперь работает как auto-selection и разворачивается в `go_library_handbook` или `monorepo_web_app_handbook`, когда признаки достаточно явные;
- явные `go_library_handbook`/`monorepo_web_app_handbook` поддерживаются как manual override;
- выбранный effective template, requested template и classification summary сохраняются в manifest/run summary;
- добавлены typed section sets для Cobra-like Go library и image-board-like monorepo web app.

### DOCS-016B — Передавать section-specific instructions в prompt contract
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-016`
- Goal: typed templates должны управлять не только retrieval-запросами и названиями секций, но и тем, что LLM обязана раскрыть в каждой секции.
- Tasks:
- расширить `SectionTemplate` полями вроде `purpose`, `must_cover`, `avoid`, `output_style`;
- добавить `section_spec` в prompt contract каждой секции;
- для `go_library_handbook` явно описать ожидания к public API, lifecycle, flags/args, completions, doc generation и testing;
- для `monorepo_web_app_handbook` явно описать ожидания к service map, local development, request flows, API surface, frontend и deployment;
- обновить developer prompt: следовать `section_spec`, не смешивать соседние секции и не превращать overview в полный inventory;
- покрыть тестами наличие section-specific instructions в prompt contract.
- Acceptance:
- prompt contract содержит machine-readable спецификацию секции помимо evidence;
- typed templates дают модели конкретные задачи для секции, а не только набор keyword retrieval hints;
- `DOCS-017` может переиспользовать те же section specs при раскладке секций по intent-based documents.
- Notes:
- `SectionTemplate` расширен полями `purpose`, `must_cover`, `avoid`, `output_style` и `document_keys`;
- `section_spec` передается в prompt contract и user payload, а developer instructions требуют следовать спецификации секции;
- typed templates теперь явно задают ожидания для Go library/CLI и monorepo web app секций;
- `cobra` в retrieval queries оставлен только как framework hint, а не как механизм классификации.

### DOCS-017 — Разделить документацию на intent-based artifacts
- Priority: `P1`
- Status: `completed`
- Depends on: `DOCS-016`, `DOCS-016B`
- Goal: генерировать не один большой handbook, а набор полезных документов под разные сценарии чтения.
- Tasks:
- добавить `repository_brief.md`: краткое понимание проекта за 1-2 страницы;
- добавить `onboarding_guide.md`: как поднять, проверить и начать менять проект;
- добавить `architecture_map.md`: структура, компоненты, зависимости, ключевые flows;
- добавить reference artifacts: API routes, env/config, commands, package/service index;
- вынести commit-derived выводы в отдельный `change_report.md`;
- обновить manifest/schema так, чтобы documents и sections были разными уровнями.
- Acceptance:
- основной документ не перегружен inventory/reference деталями;
- change history не загрязняет текущую архитектурную документацию;
- пользователь может открыть короткий brief или глубокий reference в зависимости от задачи.
- Notes:
- generation остается section-based, но публикация теперь собирает отдельные reader-facing artifacts: `repository_brief.md`, `onboarding_guide.md`, `architecture_map.md`, `api_reference.md`, `configuration_reference.md`, `commands_reference.md`, `package_service_index.md`, `change_report.md`;
- `documentation.md` стал index-документом с ссылками на generated artifacts;
- `manifest.schema-v2.json` разделяет `documents[]` и `sections[]`;
- `change_report` добавлен как отдельная section template, а commit evidence больше не добавляется в `overview`, `major_flows` и `known_gaps`.

### DOCS-018 — Нормализовать commit evidence перед LLM
- Priority: `P0`
- Status: `completed`
- Depends on: `DOCS-015`
- Goal: не допускать склеивания SHA/message/status соседних коммитов и не выводить текущее состояние проекта только из истории.
- Tasks:
- строить `change_events` с атомарными facts: `sha`, `short_sha`, `subject`, `path`, `status`, `change_type`, `current_file_present`;
- явно разделять commit facts и current snapshot facts;
- запрещать в prompt делать утверждения о текущем наличии/отсутствии файла только по историческому `deleted`;
- для merge-heavy repos группировать merge commits и original commits отдельно;
- добавить regression fixture на кейс image-board `docker-compose.yml`: `cbba05f4...` удалил файл, `733280ed...` добавил файл с message `fucking docker compose`;
- использовать commit evidence в main docs только как "recent changes", а detailed risks переносить в `change_report`.
- Acceptance:
- модель не смешивает SHA одного коммита с message другого;
- утверждение о наличии `docker-compose.yml` проверяется по текущему file inventory/project model;
- commit-derived known gaps становятся осторожными и проверяемыми.
- Notes:
- commit evidence теперь строится как `change_events` с атомарными `sha`/`subject`/`path`/`status`/`change_type`/`current_file_state`;
- prompt explicitly запрещает делать вывод о текущем отсутствии файла только по historical `deleted`;
- добавлен regression test на image-board `docker-compose.yml`, где SHA, subject и статус не должны склеиваться между соседними коммитами.

## Epic GATEWAY — Public API Integration

### GATEWAY-001 — Подключить новые маршруты в EdgeGateway
- Priority: `P0`
- Depends on: `REPO-004`, `CHAT-003`
- Goal: дать единый публичный доступ к новым сервисам.
- Tasks:
- добавить YARP routes для RepositoryService и ChatService;
- добавить маршруты для SSE endpoints;
- удалить публичную зависимость на legacy repos/chats services.
- Acceptance:
- весь основной публичный трафик идет через gateway в новые сервисы.

### GATEWAY-002 — Нормализовать auth/user context contract
- Priority: `P0`
- Depends on: `GATEWAY-001`, `PLATFORM-002`
- Goal: полностью убрать `user_id` из клиентских payload.
- Tasks:
- убедиться, что gateway всегда пробрасывает `X-User-Id`;
- обновить frontend/shared DTO;
- добавить integration tests на user context propagation.
- Acceptance:
- ни один новый публичный endpoint не требует `user_id` в body/query.

## Epic FRONT — Backend-first UI Adaptation

### FRONT-001 — Обновить shared API contracts
- Priority: `P1`
- Depends on: `GATEWAY-001`
- Goal: синхронизировать frontend с новой бэкенд-моделью.
- Tasks:
- заменить legacy endpoints `repo-index-states`, `ingest/repo`, старые chats contracts;
- добавить DTO для `snapshot`, `index_run`, `documentation_run`, SSE events;
- убрать `user_id` из payload.
- Acceptance:
- frontend/shared не содержит legacy domain model для новых потоков.

### FRONT-002 — Перевести экран индексации на SSE
- Priority: `P1`
- Depends on: `REPO-005`, `FRONT-001`
- Goal: убрать polling и показывать реальные стадии job.
- Tasks:
- подписываться на `index_run` SSE;
- показывать `stage`, `progress`, `error_message`;
- обновлять список snapshot после завершения.
- Acceptance:
- индексация отображается через streaming status updates.

### FRONT-003 — Добавить UI для документации
- Priority: `P2`
- Depends on: `DOCS-004`, `FRONT-001`
- Goal: дать минимальную возможность запускать генерацию и смотреть результат.
- Tasks:
- добавить кнопку generate docs;
- показать список documentation runs;
- показать markdown preview/download links.
- Acceptance:
- пользователь может с фронта запустить генерацию и открыть артефакты.

### FRONT-004 — Добавить chat streaming и sources UI
- Priority: `P2`
- Depends on: `CHAT-005`
- Goal: отобразить сильные стороны новой chat модели.
- Tasks:
- стримить assistant reply;
- показывать normalized sources отдельно от raw markdown;
- отображать snapshot context текущего чата.
- Acceptance:
- UI чата отражает snapshot-aware и source-aware модель.

## Epic OBS — Observability And Diagnostics

### OBS-001 — Покрыть новые сервисы и workers метриками
- Priority: `P1`
- Depends on: `REPO-001`, `CHAT-001`, `INGEST-001`, `DOCS-001`
- Goal: видеть состояние jobs и latency критических путей.
- Tasks:
- добавить metrics для queue depth, claim latency, run duration, failure counts;
- добавить retrieval, embedding, qdrant, llm latency metrics;
- добавить docs verification metrics.
- Acceptance:
- Grafana/Prometheus показывают состояние новых потоков.

### OBS-002 — Добавить structured event logging для jobs
- Priority: `P1`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: упростить разбор проблем с тяжелыми задачами.
- Tasks:
- логировать transitions job state/stage;
- логировать worker claim/release/retry;
- добавлять `run_id`, `snapshot_id`, `repository_id`, `worker_id` в контекст.
- Acceptance:
- по логам можно проследить полный lifecycle job.

## Epic TEST — Automated Verification

### TEST-001 — Написать integration tests для RepositoryService
- Priority: `P0`
- Depends on: `REPO-004`
- Goal: закрепить новую доменную модель и REST контракты.
- Tasks:
- тесты на repository create/list/get;
- тесты на snapshot lookup;
- тесты на creation of index/doc runs;
- тесты на SSE/status endpoints.
- Acceptance:
- базовый orchestration layer покрыт интеграционно.

### TEST-002 — Написать concurrency tests для jobs
- Priority: `P0`
- Depends on: `JOBS-002`, `JOBS-003`
- Goal: убедиться, что claim/lease работает надежно.
- Tasks:
- тест на конкурентный claim одной задачи;
- тест на stale recovery;
- тест на retry exhaustion.
- Acceptance:
- основные race conditions покрыты тестами.

### TEST-003 — Написать end-to-end test `index -> chat -> docs`
- Priority: `P1`
- Depends on: `CHAT-003`, `DOCS-004`
- Goal: проверить целостность всей новой системы.
- Tasks:
- поднять compose-test stack;
- проиндексировать небольшой Go repo;
- задать вопрос в чат;
- сгенерировать developer handbook;
- проверить наличие artifacts и sources.
- Acceptance:
- один e2e сценарий подтверждает работоспособность целевого use case.

## Epic OPS — Security, Limits, Reliability

### OPS-001 — Ограничить входные репозитории и ресурсы
- Priority: `P1`
- Depends on: `REPO-002`, `INGEST-002`
- Goal: предотвратить опасные и слишком тяжелые входы.
- Tasks:
- разрешить только public GitHub URL;
- ограничить repo size, file count, total bytes, clone timeout;
- ограничить поддерживаемые git protocols;
- отказоустойчиво обрабатывать oversized repository.
- Acceptance:
- система не пытается безгранично индексировать произвольные входы.

### OPS-002 — Ввести cleanup и GC для временных ресурсов
- Priority: `P1`
- Depends on: `INGEST-001`, `DOCS-001`
- Goal: не копить мусор на диске и в storage.
- Tasks:
- удалять temp clone dirs;
- удалять orphaned partial artifacts после failed jobs;
- реализовать cleanup stale local worker state.
- Acceptance:
- длительная работа системы не раздувает диск бесконтрольно.

### OPS-003 — Добавить rate limits и idempotency controls
- Priority: `P2`
- Depends on: `GATEWAY-001`, `REPO-004`, `CHAT-003`
- Goal: защитить сервисы от лишней нагрузки и дублей.
- Tasks:
- ограничить частоту index/doc/chat requests;
- добавить idempotency key для create run endpoints;
- корректно отвечать на повторные запросы.
- Acceptance:
- повторные клики пользователя не ломают систему и не плодят дублей.

## Epic LEGACY — Legacy Decommission

### LEGACY-001 — Удалить публичное использование legacy repos/chats сервисов
- Priority: `P1`
- Depends on: `GATEWAY-001`, `FRONT-001`
- Goal: перевести пользовательские сценарии на новые сервисы.
- Tasks:
- убрать legacy routes из gateway;
- убрать legacy env vars из compose;
- убедиться, что frontend больше не использует старые endpoints.
- Acceptance:
- основной пользовательский поток не зависит от `backend/repos_service` и `backend/chats_service`.

### LEGACY-002 — Удалить legacy схемы и код после стабилизации
- Priority: `P2`
- Depends on: `LEGACY-001`, `TEST-003`
- Goal: сократить техдолг после миграции.
- Tasks:
- удалить legacy repos/chats services;
- удалить устаревший `db-init`;
- удалить неактуальные workflow/config fragments;
- переписать `README.md` под новую архитектуру.
- Acceptance:
- в репозитории не осталось активно используемого legacy кода для замененных сервисов.

## Suggested First Implementation Slice

Актуализация: базовый slice уже расширен выполненными `INGEST-008`-`INGEST-022`, затем закрыты `RAG-001`-`RAG-005`, `CHAT-002`/`CHAT-003`, `JOBS-003`/`DOCS-001` и `DOCS-002`-`DOCS-004`. `RAG-006` осознанно отложен; следующий практичный шаг — ручной прогон `index -> documentation`, затем либо `DOCS-005`/`DOCS-006`, либо gateway/front wiring для demo flow.

Если нужно начать немедленно и без дополнительной декомпозиции, первый рабочий срез такой:

1. `ARCH-001`
2. `ARCH-002`
3. `DATA-001`
4. `DATA-002`
5. `DATA-003`
6. `PLATFORM-001`
7. `PLATFORM-002`
8. `REPO-001`
9. `REPO-002`
10. `REPO-003`
11. `JOBS-001`
12. `JOBS-002`
13. `INGEST-001`
14. `INGEST-002`
15. `INGEST-003`
16. `INGEST-004`
17. `INGEST-005`
18. `INGEST-006`
19. `INGEST-007`
20. `RAG-001`
21. `RAG-002`
22. `RAG-003`
23. `RAG-004A`
24. `RAG-004B`
25. `RAG-004C`
26. `RAG-004`
27. `RAG-005`
28. `RAG-006`
29. `REPO-004`
30. `CHAT-001`
31. `CHAT-002`
32. `CHAT-003`
33. `GATEWAY-001`
34. `GATEWAY-002`
35. `TEST-001`
36. `TEST-002`

После этого проект уже сможет:

- регистрировать репозиторий;
- запускать индексацию через durable job;
- строить snapshot и промежуточные analysis artifacts;
- индексировать чанки в Qdrant;
- отвечать на вопросы по snapshot через новый `ChatService`.

Следующий обязательный слой после этого:

1. `REPO-005`
2. `DOCS-001`
3. `DOCS-002`
4. `DOCS-003`
5. `DOCS-004`
6. `DOCS-008`
7. `FRONT-002`
8. `TEST-003`
