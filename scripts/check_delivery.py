"""Reject unresolved Git conflict markers in allowlisted delivery text."""

import re
from pathlib import Path

from scripts.package_release import release_files

TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yml", ".yaml", ".lock", ".txt"}
MARKER = re.compile(r"^(?:<{7}(?:\s.*)?|={7}|>{7}(?:\s.*)?|\|{7}(?:\s.*)?)\s*$", re.M)


def validate_delivery_text(text: str, name: str) -> None:
    if MARKER.search(text):
        raise ValueError(f"Unresolved Git conflict marker in delivery file: {name}")


def check_delivery(root: Path) -> None:
    for path in release_files(root):
        if path.suffix in TEXT_SUFFIXES:
            validate_delivery_text(path.read_text(encoding="utf-8"), str(path.relative_to(root)))


if __name__ == "__main__":
    check_delivery(Path(__file__).resolve().parents[1])
    print("PASS: delivery sources contain no unresolved Git conflict markers")
