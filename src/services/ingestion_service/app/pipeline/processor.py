from hashlib import sha1
from pathlib import Path
from app.core.config import settings
from app.pipeline.traversal import iterate_source_files


def process_repo_and_upsert(root_path: Path, repo_name: str, treesitter, embedder, qdrant):
    qdrant.init_collection(settings.vector_size)

    for file_path in iterate_source_files(root_path):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        file_hash = sha1(text.encode('utf-8')).hexdigest()
        rel_path = str(file_path.relative_to(root_path))
        language = "Dockerfile" if file_path.name == "Dockerfile" else file_path.suffix.lstrip(".")

        chunks = []
        if language == "go":
            file_data = treesitter.extract_go_entities(text, file_path)
            package = file_data["package"] or ""
            imports = "\n".join(file_data["imports"])
            for entity in file_data["entities"]:
                src = entity["src"]
                if embedder.count_tokens(src) > settings.max_tokens:
                    for _, _, ctext in embedder.chunk_by_tokens(src, settings.max_tokens, settings.overlap):
                        chunks.append((rel_path, package, imports, entity, ctext))
                else:
                    chunks.append((rel_path, package, imports, entity, src))
        else:
            for _, _, ctext in embedder.chunk_by_tokens(text, settings.max_tokens, settings.overlap):
                chunks.append((rel_path, "", "", None, ctext))

        sentences = [c[4] for c in chunks]
        if not sentences:
            continue

        embeddings = embedder.encode(sentences, prompt_name="code2code_document")

        for idx, (rel_path, package, imports, entity, src) in enumerate(chunks):
            payload = {
                "repo": repo_name,
                "file_path": rel_path,
                "language": language,
                "chunk_index": idx,
                "body": src,
            }
            if entity:
                payload |= {
                    "package": package,
                    "imports": imports,
                    "kind": entity["kind"],
                    "name": entity["name"],
                    "start_code_line": entity["start"],
                    "end_code_line": entity["end"],
                }

            qdrant.add_point_from_vector(
                file_hash=file_hash,
                chunk_index=idx,
                vector=embeddings[idx].astype(float).tolist(),
                payload=payload,
            )

    qdrant.flush()
    return qdrant.total_upserted
