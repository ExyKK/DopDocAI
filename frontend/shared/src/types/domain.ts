export type UUID = string;

export type JobRunStatus =
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "canceled"
    | "stale"
    | string;

export type MessageRole = "user" | "assistant";

export interface Repository {
    id: UUID;
    provider?: string;
    host?: string;
    owner?: string;
    name?: string;
    full_name: string;
    url: string;
    selected_branch: string | null;
    default_branch: string | null;
    active_snapshot_id: UUID | null;
    created_at: string;
    updated_at?: string;
}

export interface RepositorySnapshot {
    id: UUID;
    repository_id: UUID;
    branch_name: string;
    commit_sha: string;
    tree_hash: string;
    commit_subject: string | null;
    files_total: number;
    go_files_total: number;
    readme_files_total: number;
    bytes_total: number;
    created_at: string;
}

export interface IndexRun {
    id: UUID;
    repository_id: UUID;
    snapshot_id: UUID | null;
    status: JobRunStatus;
    stage: string;
    progress_pct: number;
    progress_current: number;
    progress_total: number;
    attempt: number;
    max_attempts: number;
    error_code: string | null;
    error_message: string | null;
    embedding_model: string | null;
    files_processed: number;
    chunks_total: number;
    symbols_total: number;
    vectors_upserted: number;
    started_at: string | null;
    finished_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface DocumentationRun {
    id: UUID;
    repository_id: UUID;
    snapshot_id: UUID;
    source_index_run_id: UUID | null;
    template_kind: string;
    requested_template_kind: string;
    effective_template_kind: string | null;
    status: JobRunStatus;
    stage: string;
    progress_pct: number;
    progress_current: number;
    progress_total: number;
    attempt: number;
    max_attempts: number;
    model_name: string | null;
    error_code: string | null;
    error_message: string | null;
    published_manifest_artifact_id: UUID | null;
    started_at: string | null;
    finished_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface DocumentationArtifact {
    id: UUID;
    documentation_run_id: UUID;
    section_id: UUID | null;
    attempt: number;
    artifact_kind: string;
    storage_bucket: string;
    storage_key: string;
    content_type: string;
    format: string;
    checksum_sha256: string;
    size_bytes: number;
    schema_version: number;
    created_at: string;
}

export interface Chat {
    id: UUID;
    repository_id: UUID;
    snapshot_id: UUID;
    title: string | null;
    created_at: string;
    updated_at: string;
    last_message_at: string | null;
}

export interface ChatMessageSource {
    ordinal: number;
    snapshot_id: UUID;
    source_kind: string;
    file_path: string | null;
    symbol_name: string | null;
    start_line: number | null;
    end_line: number | null;
    chunk_id: string | null;
    score: number | null;
    used_in_answer: boolean;
    citation_label: string | null;
}

export interface ChatMessage {
    id: UUID;
    chat_id: UUID;
    role: MessageRole;
    content_markdown: string;
    model_name: string | null;
    provider: string | null;
    finish_reason: string | null;
    created_at: string;
    sources: ChatMessageSource[];
}
