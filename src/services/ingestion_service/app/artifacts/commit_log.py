import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from git import GitCommandError, Repo

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key

COMMIT_LOG_ARTIFACT_KIND = "commit_log"
COMMIT_LOG_SCHEMA_VERSION = 1
DEFAULT_MAX_COMMITS = 50


def build_commit_log_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    package_graph_artifact: BuiltAnalysisArtifact | dict[str, Any] | None = None,
    *,
    max_commits: int = DEFAULT_MAX_COMMITS,
) -> BuiltAnalysisArtifact:
    if max_commits < 1:
        raise ValueError("max_commits must be greater than or equal to 1")

    repo = Repo(Path(repo_path))
    package_graph = _load_artifact_document(package_graph_artifact)
    package_lookup = _build_package_lookup(package_graph)
    base_snapshot_id = _optional_text(snapshot_metadata.get("base_snapshot_id"))
    base_commit_sha = _base_commit_sha(snapshot_metadata)
    head_commit_sha = snapshot_metadata["commit_sha"].lower()

    range_info, commits = _collect_commits(
        repo,
        head_commit_sha=head_commit_sha,
        base_snapshot_id=base_snapshot_id,
        base_commit_sha=base_commit_sha,
        base_snapshot_fallback_reason=_optional_text(
            snapshot_metadata.get("base_snapshot_fallback_reason")
        ),
        max_commits=max_commits,
    )
    commit_records, touched_files, touched_packages, change_type_counts = _build_change_records(
        repo,
        commits,
        package_lookup,
    )

    summary = {
        "commits_total": len(commit_records),
        "commits_available": range_info["commits_available"],
        "max_commits": max_commits,
        "truncated": range_info["truncated"],
        "has_base_snapshot": base_snapshot_id is not None,
        "base_commit_reachable": range_info["base_commit_reachable"],
        "touched_files_total": len(touched_files),
        "touched_go_files_total": sum(1 for item in touched_files if item["path"].endswith(".go")),
        "touched_packages_total": len(touched_packages),
        "merge_commits_total": sum(1 for item in commit_records if item["is_merge"]),
        "change_type_counts": dict(sorted(change_type_counts.items())),
    }

    document = {
        "artifact_kind": COMMIT_LOG_ARTIFACT_KIND,
        "schema_version": COMMIT_LOG_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": summary,
        "range": range_info,
        "commits": commit_records,
        "touched_files": touched_files,
        "touched_packages": touched_packages,
        "source_artifacts": _source_artifacts(package_graph_artifact),
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=COMMIT_LOG_ARTIFACT_KIND,
        schema_version=COMMIT_LOG_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=analysis_artifact_storage_key(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            artifact_kind=COMMIT_LOG_ARTIFACT_KIND,
            schema_version=COMMIT_LOG_SCHEMA_VERSION,
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=len(commit_records),
        payload=payload,
        summary=summary,
    )


def _collect_commits(
    repo: Repo,
    *,
    head_commit_sha: str,
    base_snapshot_id: str | None,
    base_commit_sha: str | None,
    base_snapshot_fallback_reason: str | None,
    max_commits: int,
) -> tuple[dict[str, Any], list[Any]]:
    base_commit_reachable: bool | None = None
    mode = "recent"
    revision = head_commit_sha

    if base_commit_sha is not None:
        base_commit_reachable = _is_ancestor(repo, base_commit_sha, head_commit_sha)
        if base_commit_reachable:
            mode = "base_to_head"
            revision = f"{base_commit_sha}..{head_commit_sha}"

    commits_available = _revision_count(repo, revision)
    commits = list(repo.iter_commits(revision, max_count=max_commits))
    range_info = {
        "mode": mode,
        "head_commit_sha": head_commit_sha,
        "base_snapshot_id": base_snapshot_id,
        "base_commit_sha": base_commit_sha,
        "base_commit_reachable": base_commit_reachable,
        "fallback_reason": _range_fallback_reason(
            base_snapshot_id=base_snapshot_id,
            base_commit_sha=base_commit_sha,
            base_commit_reachable=base_commit_reachable,
            explicit_reason=base_snapshot_fallback_reason,
        ),
        "revision": revision,
        "max_commits": max_commits,
        "commits_available": commits_available,
        "truncated": commits_available > len(commits),
    }

    return range_info, commits


def _build_change_records(
    repo: Repo,
    commits: list[Any],
    package_lookup: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    commit_records: list[dict[str, Any]] = []
    files_by_path: dict[str, dict[str, Any]] = {}
    packages_by_id: dict[str, dict[str, Any]] = {}
    change_type_counts: Counter[str] = Counter()

    for commit in commits:
        changed_files = _changed_files_for_commit(repo, commit.hexsha)
        commit_change_counts = Counter(file_record["change_type"] for file_record in changed_files)
        change_type_counts.update(commit_change_counts)

        for file_record in changed_files:
            packages = _packages_for_path(file_record["path"], package_lookup)
            file_record["packages"] = packages
            _aggregate_touched_file(files_by_path, commit.hexsha, file_record)
            for package in packages:
                _aggregate_touched_package(packages_by_id, commit.hexsha, file_record, package)

        touched_packages = sorted(
            {
                package["package_id"]: package
                for file_record in changed_files
                for package in file_record["packages"]
            }.values(),
            key=lambda item: item["package_id"],
        )
        message = commit.message.strip()
        commit_records.append(
            {
                "sha": commit.hexsha.lower(),
                "short_sha": commit.hexsha[:12].lower(),
                "parents": [parent.hexsha.lower() for parent in commit.parents],
                "is_merge": len(commit.parents) > 1,
                "subject": _subject(message),
                "message": message or None,
                "author": {
                    "name": _optional_text(commit.author.name),
                    "email": _optional_text(commit.author.email),
                    "time": _json_datetime(commit.authored_datetime),
                },
                "committer": {
                    "name": _optional_text(commit.committer.name),
                    "email": _optional_text(commit.committer.email),
                    "time": _json_datetime(commit.committed_datetime),
                },
                "change_type_counts": dict(sorted(commit_change_counts.items())),
                "touched_files": changed_files,
                "touched_packages": touched_packages,
            }
        )

    touched_files = [_finalize_touched_file(value) for value in files_by_path.values()]
    touched_files.sort(key=lambda item: item["path"])
    touched_packages = [_finalize_touched_package(value) for value in packages_by_id.values()]
    touched_packages.sort(key=lambda item: item["package_id"])

    return commit_records, touched_files, touched_packages, change_type_counts


def _changed_files_for_commit(repo: Repo, commit_sha: str) -> list[dict[str, Any]]:
    try:
        output = repo.git.diff_tree(
            "--no-commit-id",
            "--name-status",
            "-r",
            "--root",
            "-M",
            commit_sha,
        )
    except GitCommandError:
        return []

    files: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        parsed = _parse_name_status_line(raw_line)
        if parsed is not None:
            files.append(parsed)

    files.sort(key=lambda item: (item["path"], item.get("old_path") or "", item["status"]))
    return files


def _parse_name_status_line(line: str) -> dict[str, Any] | None:
    parts = line.split("\t")
    if len(parts) < 2:
        return None

    status = parts[0]
    status_code = status[:1]
    if status_code in {"R", "C"} and len(parts) >= 3:
        old_path = _normalize_path(parts[1])
        path = _normalize_path(parts[2])
    else:
        old_path = None
        path = _normalize_path(parts[1])

    return {
        "path": path,
        "old_path": old_path,
        "status": status,
        "change_type": _change_type(status_code),
    }


def _aggregate_touched_file(
    files_by_path: dict[str, dict[str, Any]],
    commit_sha: str,
    file_record: dict[str, Any],
) -> None:
    path = file_record["path"]
    builder = files_by_path.setdefault(
        path,
        {
            "path": path,
            "old_paths": set(),
            "commit_shas": [],
            "change_type_counts": Counter(),
            "packages": {},
        },
    )

    if commit_sha not in builder["commit_shas"]:
        builder["commit_shas"].append(commit_sha.lower())
    if file_record.get("old_path"):
        builder["old_paths"].add(file_record["old_path"])
    builder["change_type_counts"].update([file_record["change_type"]])
    for package in file_record["packages"]:
        builder["packages"][package["package_id"]] = package


def _aggregate_touched_package(
    packages_by_id: dict[str, dict[str, Any]],
    commit_sha: str,
    file_record: dict[str, Any],
    package: dict[str, Any],
) -> None:
    package_id = package["package_id"]
    builder = packages_by_id.setdefault(
        package_id,
        {
            **package,
            "commit_shas": [],
            "touched_files": set(),
            "change_type_counts": Counter(),
        },
    )

    if commit_sha not in builder["commit_shas"]:
        builder["commit_shas"].append(commit_sha.lower())
    builder["touched_files"].add(file_record["path"])
    builder["change_type_counts"].update([file_record["change_type"]])


def _finalize_touched_file(builder: dict[str, Any]) -> dict[str, Any]:
    commit_shas = builder["commit_shas"]
    return {
        "path": builder["path"],
        "old_paths": sorted(builder["old_paths"]),
        "commits_total": len(commit_shas),
        "latest_commit_sha": commit_shas[0] if commit_shas else None,
        "earliest_commit_sha": commit_shas[-1] if commit_shas else None,
        "commit_shas": commit_shas,
        "change_type_counts": dict(sorted(builder["change_type_counts"].items())),
        "packages": sorted(builder["packages"].values(), key=lambda item: item["package_id"]),
    }


def _finalize_touched_package(builder: dict[str, Any]) -> dict[str, Any]:
    commit_shas = builder["commit_shas"]
    touched_files = sorted(builder["touched_files"])
    return {
        "package_id": builder["package_id"],
        "dir_path": builder["dir_path"],
        "import_path": builder["import_path"],
        "name": builder["name"],
        "commits_total": len(commit_shas),
        "files_total": len(touched_files),
        "commit_shas": commit_shas,
        "touched_files": touched_files,
        "change_type_counts": dict(sorted(builder["change_type_counts"].items())),
    }


def _build_package_lookup(package_graph: dict[str, Any] | None) -> dict[str, Any]:
    by_file: dict[str, list[dict[str, Any]]] = {}
    by_dir: dict[str, list[dict[str, Any]]] = {}
    if not package_graph:
        return {"by_file": by_file, "by_dir": by_dir}

    for package in package_graph.get("packages", []):
        ref = {
            "package_id": package["package_id"],
            "dir_path": package["dir_path"],
            "import_path": package.get("import_path"),
            "name": package["name"],
        }
        by_dir.setdefault(package["dir_path"], []).append(ref)
        for file_path in package.get("files", []):
            by_file.setdefault(_normalize_path(file_path), []).append(ref)

    for refs in by_file.values():
        refs.sort(key=lambda item: item["package_id"])
    for refs in by_dir.values():
        refs.sort(key=lambda item: item["package_id"])

    return {"by_file": by_file, "by_dir": by_dir}


def _packages_for_path(path: str, package_lookup: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalize_path(path)
    by_file = package_lookup["by_file"]
    if normalized in by_file:
        return [dict(item) for item in by_file[normalized]]

    matching_dirs = sorted(
        (
            dir_path
            for dir_path in package_lookup["by_dir"]
            if _path_belongs_to_dir(normalized, dir_path)
        ),
        key=lambda item: (-len(PurePosixPath(item).parts), item),
    )
    if not matching_dirs:
        return []

    return [dict(item) for item in package_lookup["by_dir"][matching_dirs[0]]]


def _load_artifact_document(
    artifact: BuiltAnalysisArtifact | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if artifact is None:
        return None

    if isinstance(artifact, BuiltAnalysisArtifact):
        return json.loads(artifact.payload.decode("utf-8"))

    return artifact


def _source_artifacts(artifact: BuiltAnalysisArtifact | dict[str, Any] | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []

    if isinstance(artifact, BuiltAnalysisArtifact):
        return [
            {
                "artifact_kind": artifact.artifact_kind,
                "schema_version": artifact.schema_version,
                "storage_key": artifact.storage_key,
                "checksum_sha256": artifact.checksum_sha256,
            }
        ]

    return [
        {
            "artifact_kind": artifact.get("artifact_kind"),
            "schema_version": artifact.get("schema_version"),
        }
    ]


def _base_commit_sha(snapshot_metadata: dict[str, Any]) -> str | None:
    candidates = (
        snapshot_metadata.get("base_commit_sha"),
        snapshot_metadata.get("base_snapshot_commit_sha"),
        snapshot_metadata.get("previous_commit_sha"),
    )
    for candidate in candidates:
        normalized = _optional_text(candidate)
        if normalized is not None:
            return normalized.lower()

    base_snapshot = snapshot_metadata.get("base_snapshot")
    if isinstance(base_snapshot, dict):
        normalized = _optional_text(base_snapshot.get("commit_sha"))
        if normalized is not None:
            return normalized.lower()

    return None


def _revision_count(repo: Repo, revision: str) -> int:
    try:
        return int(repo.git.rev_list("--count", revision).strip())
    except (GitCommandError, ValueError):
        return 0


def _is_ancestor(repo: Repo, ancestor_sha: str, head_sha: str) -> bool:
    try:
        repo.git.merge_base("--is-ancestor", ancestor_sha, head_sha)
        return True
    except GitCommandError:
        return False


def _range_fallback_reason(
    *,
    base_snapshot_id: str | None,
    base_commit_sha: str | None,
    base_commit_reachable: bool | None,
    explicit_reason: str | None,
) -> str | None:
    if base_commit_reachable is True:
        return None

    if explicit_reason is not None:
        return explicit_reason

    if base_commit_sha is None:
        return "base_snapshot_missing" if base_snapshot_id is None else "base_commit_missing"

    if base_commit_reachable is False:
        return "base_commit_unreachable"

    return "base_snapshot_missing"


def _change_type(status_code: str) -> str:
    return {
        "A": "added",
        "C": "copied",
        "D": "deleted",
        "M": "modified",
        "R": "renamed",
        "T": "type_changed",
        "U": "unmerged",
        "X": "unknown",
        "B": "broken_pairing",
    }.get(status_code, "unknown")


def _path_belongs_to_dir(path: str, dir_path: str) -> bool:
    if dir_path == ".":
        return "/" not in path

    return path == dir_path or path.startswith(f"{dir_path}/")


def _normalize_path(path: str) -> str:
    return str(PurePosixPath(path))


def _subject(message: str) -> str | None:
    if not message:
        return None

    return message.splitlines()[0]


def _json_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
