from pathlib import Path
from typing import List


def is_binary(path: Path) -> bool:
    # quick heuristic
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            if b"\0" in chunk:
                return True
            # high non-text ratio
            nontext = sum(1 for b in chunk if b < 9 or (b > 13 and b < 32))
            return (nontext / max(1, len(chunk))) > 0.3
    except Exception:
        return True


def iterate_source_files(root: Path, extentions: List[str] = None, exclude_dirs: List[str] = None):
    """
    Iterator function, returns appropriate files
    """
    if extentions is None:
        extentions = [".go", ".mod", ".md", ".yaml", ".yml", ".json", ".toml", ".ts", ".tsx", ".css", ".html"]
    if exclude_dirs is None:
        exclude_dirs = [".git", "vendor", "node_modules", "bin", ".venv", "__pycache__"]
    for path in root.rglob("*"):
        if path.is_file():
            if any(part in exclude_dirs for part in path.parts):
                continue
            # special-case Dockerfile and other name-based files (no suffix)
            if path.name == "Dockerfile" or path.suffix.lower() in extentions:
                if not is_binary(path):
                    yield path