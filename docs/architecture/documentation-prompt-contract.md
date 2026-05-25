# Documentation Evidence Packs And Prompt Contract

`DOCS-008`, `DOCS-008B`, `DOCS-009`, `DOCS-011`, `DOCS-014`, `DOCS-015`,
`DOCS-016B`, `DOCS-017` and `DOCS-018` define the handoff between repository
evidence, LLM-backed section generation, verification and repair. The pipeline
must send bounded, auditable and rendered inputs to the model instead of raw
analysis artifacts.

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

The documentation worker writes a debug/verification artifact:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/evidence_packs.schema-v1.json
```

## Rendered Evidence Pack

Each raw pack is converted to a rendered pack before prompt construction:

- structured artifacts are rendered as Markdown lists/tables rather than nested
  JSON arrays;
- project/package/config/commit fields use dedicated renderers;
- retrieval chunks keep concise excerpts with file/symbol/line provenance;
- generated Swagger/codegen retrieval chunks are filtered from generic handbook
  sections by default;
- commit history is normalized into atomic `change_events` with `sha`,
  `short_sha`, `subject`, `path`, `status`, `change_type` and
  `current_file_state`.

The rendered pack is also published for debugging:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/rendered_evidence_packs.schema-v1.json
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
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/prompt_contracts.schema-v1.json
```

`DOCS-010`/`DOCS-012` use this contract as the input to the LLM provider layer.
Production-like runs call the configured external provider, while `stub` mode
keeps deterministic smoke generation available without network calls.

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
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/verification_report.schema-v1.json
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

Repair artifacts:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/repair_plan.schema-v1.json
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/repair_attempts.schema-v1.json
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/sections/{section_key}.attempt-{n}.md
```

After a repair attempt the pipeline republishes the final section markdown,
rebuilds affected intent-based documents, rebuilds `documentation.md`, updates
`manifest.schema-v2.json` and verifies the new set again.

## Template Selection

`DOCS-016` adds artifact-driven repository classification before section
planning. The default `developer_handbook` request is treated as auto-selection:

- Cobra-like Go libraries and CLI/library packages use `go_library_handbook`;
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

The manifest is published as `manifest.schema-v2.json`. Its top level now has
separate `documents[]` and `sections[]` arrays: documents describe reader-facing
artifacts, while sections preserve generation metadata, section specs, source
counts and per-section artifact links.
