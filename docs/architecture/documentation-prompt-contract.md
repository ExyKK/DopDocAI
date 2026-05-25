# Documentation Evidence Packs And Prompt Contract

`DOCS-008`, `DOCS-008B`, `DOCS-009`, `DOCS-011`, `DOCS-014`, `DOCS-015`,
`DOCS-016B`, `DOCS-017`, `DOCS-018`, `DOCS-020`, `DOCS-021`, `DOCS-008C`
and `DOCS-023` define the
handoff between repository evidence, LLM-backed section generation, verification
and repair. The pipeline must send bounded, auditable and rendered inputs to the
model instead of raw analysis artifacts.

## Evidence Pack

Each documentation section receives one evidence pack:

- `section_key`, `title`, `ordinal`;
- `budget` with max total tokens, per-source tokens and source count;
- ordered `sources` with stable source ids such as `S1`, `S2`;
- provenance fields: `file_path`, `symbol_name`, line range, `chunk_id`,
  retrieval score and selection reason;
- diagnostics: `omitted_sources`, `truncated_sources`, `estimated_tokens`;
- optional `retrieval_query` and `retrieval_error`.

The raw pack is built from compact structured evidence plus retrieval chunks.
It remains a debug artifact; prompt contracts use the rendered pack described
below. The default budget is intentionally spacious for the selected DeepSeek V4
Flash runtime:

```env
DOPDOC_DOCS_EVIDENCE_PACK_MAX_TOKENS=120000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCE_TOKENS=16000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCES=80
```

The documentation worker writes a draft debug/verification artifact under the
current job attempt:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/evidence_packs.schema-v1.json
```

## Rendered Evidence Pack

Each raw pack is converted to a rendered pack before prompt construction:

- structured artifacts are rendered as Markdown lists/tables rather than nested
  JSON arrays;
- project/package/config/commit fields use dedicated renderers;
- retrieval chunks keep concise excerpts with file/symbol/line provenance;
- generated Swagger/codegen retrieval chunks are filtered from generic handbook
  sections by default;
- Go library runtime sections prefer Go `runtime` retrieval chunks and filter
  consumer docs/examples from current-state API/command claims;
- commit history is normalized into atomic `change_events` with `sha`,
  `short_sha`, `subject`, `path`, `status`, `change_type` and
  `current_file_state`.

The rendered pack is also published for debugging:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/rendered_evidence_packs.schema-v1.json
```

## Prompt Contract

Each section prompt contract contains:

- `system` message: the model is a source-grounded documentation generator;
- `developer` message: output language, body-only markdown shape, citation,
  section-specific, commit-history and unknown evidence rules;
- `section_spec`: machine-readable `purpose`, `must_cover`, `avoid`,
  `output_style` and `document_keys` from the selected template;
- `user` message: section plan/spec, allowed source ids and rendered evidence
  sources.

Key rules:

- cite every factual claim about repository behavior, files, commands, APIs,
  dependencies or configuration with provided source ids;
- use only source ids listed in the evidence pack;
- state that evidence is missing instead of guessing;
- generate only the requested section body, without a heading or sources
  appendix;
- follow the selected section's `section_spec` and avoid drifting into topics
  assigned to sibling sections;
- do not infer current file absence from a historical `deleted` event unless
  `current_file_state` is `absent`.

The LLM output is post-processed after generation:

- leading model-generated headings are stripped and the canonical section
  heading is added by the pipeline;
- a section-local `### Sources` appendix maps `S1`, `S2`, ... to artifact/file
  provenance;
- obvious hygiene issues (`finish_reason=length`, unclosed fences, glued
  repeated words and repeated phrases) are recorded as warnings in manifest/run
  summary.

The documentation worker writes the prompt contract manifest:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/prompt_contracts.schema-v1.json
```

`DOCS-010`/`DOCS-012` use this contract as the input to the LLM provider layer.
Production-like runs call the configured external provider, while `stub` mode
keeps deterministic smoke generation available without network calls. Generation
and repair remain markdown calls; judge calls use JSON object mode by default.

## Verification And Repair

`DOCS-008` adds a verification pass after the intent-based documentation set is
assembled. The default mode is `hybrid`:

- deterministic checks validate manifest v2 shape, document/section presence,
  citation ids, body citations, short sections, unclosed code fences, raw JSON
  dumps, `finish_reason=length` and commit-hash leakage outside `change_report`;
- LLM judge checks every generated section against its prompt contract and
  rendered evidence pack;
- LLM judge also checks the full document set for intent drift, duplication,
  wrong-scope commit history and weak usefulness;
- `stub` LLM runs automatically fall back to deterministic verification so
  smoke tests remain cheap and offline.

The verifier writes:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/verification_report.schema-v1.json
```

The report contains `findings[]`, `section_scores`, `document_scores`,
`judge_calls[]` and a machine-readable `summary`. Hard `error` findings fail the
run after repair attempts are exhausted. `warning` findings keep the run
successful but mark verification as degraded.

`DOCS-008B` wraps verification in a bounded repair loop:

```text
generate -> verify -> repair -> verify
```

The loop is separate from technical job retries. It is controlled by
`DOPDOC_DOCS_MAX_REPAIR_ROUNDS`/`DOCS_MAX_REPAIR_ROUNDS` and defaults to `2`.
Only sections with repairable `error` findings are regenerated. The repair
prompt receives the current section markdown, section spec, allowed source ids,
source index, original prompt payload and relevant verification findings.
Unsupported or contradicted claims must be removed or rewritten as honest
unknown/partial statements instead of introducing new evidence.

`DOCS-008C` adds targeted evidence expansion before section repair. Repair
plans classify findings into rewrite-only, retrieval-targeted and retrieval-
blocked actions. Missing coverage, weak evidence and explicitly
`expand_evidence` judge findings can run small filtered retrieval queries using
the finding claim, `evidence_needed`, retrieval hints and section `must_cover`.
Contradicted, wrong-scope, citation and markdown hygiene findings do not trigger
retrieval, because those must be removed or rewritten against existing evidence.

When targeted retrieval finds usable matches, the pipeline creates new stable
source ids (`S{n}`), extends the in-memory prompt contract for the affected
section and passes a `repair_evidence_delta` object into the repair prompt. The
next verification round sees both original and delta source ids as allowed. If
retrieval finds no supporting evidence, the repair prompt keeps the issue as
unknown/partial instead of inventing a fact.

Repair artifacts:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/repair_plan.schema-v1.json
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/repair_evidence_delta.round-{n}.schema-v1.json
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/repair_attempts.schema-v1.json
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/sections/{section_key}.repair-{n}.md
```

After a repair attempt the pipeline republishes draft section markdown, rebuilds
draft intent-based documents under `attempts/{attempt}`, rebuilds draft
`documentation.md` and verifies the new set again. Stable root
`documentation.md`, intent documents and `manifest.schema-v2.json` are published
only after verification succeeds.

Technical LLM failures are handled before job-level retry. The same call-level
policy is used for section generation, section repair, section judge and
document-set judge:

- retry `llm_response_empty`, timeout, provider 429/5xx and invalid judge JSON
  inside the current LLM call;
- invalid judge JSON receives an extra correction message and the judge request
  uses `response_format={"type":"json_object"}` while JSON mode is enabled;
- exhausted technical retries fail the current run attempt with a diagnostic
  artifact instead of silently starting the whole documentation run over;
- quality failures from verification stay in the repair loop and then become a
  failed verification report when repair is exhausted.

Runtime knobs:

```env
DOPDOC_DOCS_LLM_CALL_MAX_ATTEMPTS=3
DOPDOC_DOCS_LLM_CALL_RETRY_DELAY_S=1
DOPDOC_DOCS_LLM_JSON_MODE_ENABLED=true
```

## Observability And Diagnostics

`DOCS-020` adds compact structured observability to the documentation pipeline.
The worker logs progress, template selection, LLM call lifecycle and artifact
publication with stable ids such as `documentation_run_id`, `attempt`,
`repository_id`, `snapshot_id`, `stage`, `section_key`, `repair_round`,
`llm_task` and `artifact_kind`.

Every trace-enabled run publishes:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/pipeline_trace.schema-v1.json
```

`pipeline_trace` is an ordered event log for stages, section generation, judge
calls, repair calls and artifact publication. It stores provider/model,
response id, finish reason, token usage, latency and retry counts, but not full
prompt or response bodies.

When a technical failure interrupts generation, verification or repair before a
normal report can be produced, the worker also publishes:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/pipeline_error.schema-v1.json
```

The error artifact contains the failed stage, section key when available,
repair round, retryable flag, sanitized provider details, completed sections and
already published artifacts for that attempt.

Runtime knobs:

```env
DOPDOC_DOCS_LOG_LEVEL=INFO
DOPDOC_DOCS_PIPELINE_TRACE_ENABLED=true
```

## Template Selection

`DOCS-016` adds artifact-driven repository classification before section
planning. The default `developer_handbook` request is treated as auto-selection:

- Cobra-like Go libraries and CLI/library packages use `go_library_handbook`;
- root Go modules without HTTP/frontend/API surface are treated as Go
  library/CLI candidates even if earlier workspace detection marked the unit as
  `backend`;
- frontend + backend monorepos use `monorepo_web_app_handbook`;
- `developer_handbook` remains the fallback for repository shapes without a
  specialized template yet.

Manual `template_kind` values `go_library_handbook` and
`monorepo_web_app_handbook` bypass classification. Each run summary and manifest
records the requested template, effective template, classification kind,
confidence, signals and scores.

## Intent-Based Output Artifacts

`DOCS-017` keeps generation section-based, but changes publication from one
large handbook body to a documentation set. The worker still publishes per-section
markdown for auditability, then assembles intent-based documents:

- `documentation.md`: index document with links to generated artifacts;
- `repository_brief.md`: short orientation;
- `onboarding_guide.md`: build/run/test/local development path;
- `architecture_map.md`: structure, components and flows;
- `api_reference.md`: API/entry point reference when supported by sections;
- `configuration_reference.md`: environment/config/deployment facts;
- `commands_reference.md`: commands, scripts, CLI flags and completions;
- `package_service_index.md`: package/service/workspace index;
- `change_report.md`: recent history, kept separate from current architecture.

During a run attempt the worker publishes draft reader-facing artifacts under:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/attempts/{attempt}/...
```

Draft artifacts use `draft_*` artifact kinds where they could otherwise be
confused with final reader-facing outputs. This keeps failed attempts useful for
debugging and diploma experiments without making them public/latest docs.

Only a successful verification pass publishes stable artifacts under:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/documentation.md
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/{document_key}.md
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/manifest.schema-v2.json
```

The manifest is published as `manifest.schema-v2.json`. Its top level has
separate `documents[]` and `sections[]` arrays: documents describe final
reader-facing artifacts, while sections preserve generation metadata, section
specs, source counts and per-section draft artifact links. RepositoryService
stores `attempt` on every `documentation_artifacts` row, so attempts remain
distinguishable in Postgres as well as in MinIO. Job-level retry currently uses
a clean-attempt strategy: it reads previous attempt metadata, records the
decision in `pipeline_trace`, and starts a new isolated attempt instead of
mixing or reusing draft artifacts. Attempt artifacts are retained as audit and
experiment material; cleanup can remove old attempts later, but final consumers
should resolve only the stable manifest artifact recorded on a successful run.
