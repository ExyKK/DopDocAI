# Documentation Evidence Packs And Prompt Contract

`DOCS-009` and `DOCS-011` define the handoff between repository evidence and
LLM-backed section generation. The pipeline must send bounded, auditable inputs
to the model instead of raw analysis artifacts.

## Evidence Pack

Each documentation section receives one evidence pack:

- `section_key`, `title`, `ordinal`;
- `budget` with max total tokens, per-source tokens and source count;
- ordered `sources` with stable source ids such as `S1`, `S2`;
- provenance fields: `file_path`, `symbol_name`, line range, `chunk_id`,
  retrieval score and selection reason;
- diagnostics: `omitted_sources`, `truncated_sources`, `estimated_tokens`;
- optional `retrieval_query` and `retrieval_error`.

The pack is built from compact structured evidence plus retrieval chunks. The
default budget is intentionally spacious for the selected DeepSeek V4 Flash
runtime:

```env
DOPDOC_DOCS_EVIDENCE_PACK_MAX_TOKENS=120000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCE_TOKENS=16000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCES=80
```

The documentation worker writes a debug/verification artifact:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/evidence_packs.schema-v1.json
```

## Prompt Contract

Each section prompt contract contains:

- `system` message: the model is a source-grounded documentation generator;
- `developer` message: output language, markdown shape, citation and unknown
  evidence rules;
- `user` message: section plan, allowed source ids and the evidence pack JSON.

Key rules:

- cite every factual claim about repository behavior, files, commands, APIs,
  dependencies or configuration with provided source ids;
- use only source ids listed in the evidence pack;
- state that evidence is missing instead of guessing;
- generate only the requested section.

The documentation worker writes the prompt contract manifest:

```text
repositories/{repository_id}/snapshots/{snapshot_id}/documentation-runs/{run_id}/prompt_contracts.schema-v1.json
```

`DOCS-010`/`DOCS-012` will use this contract as the input to the LLM provider
layer and replace deterministic section prose in the production path.
