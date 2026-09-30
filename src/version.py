"""Release version has one source of truth: pyproject.toml."""

import tomllib
from pathlib import Path


def project_version(root: Path | None = None) -> str:
    path = (root or Path(__file__).resolve().parents[1]) / "pyproject.toml"
    return str(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"])


def bundle_name() -> str:
    return f"ai-business-solution-agent-{project_version()}.zip"
