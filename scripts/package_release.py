"""Create an allowlisted source-service bundle; excludes caches, environments and agent tools."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.version import bundle_name

ROOT = Path(__file__).resolve().parents[1]


def release_files(root: Path) -> list[Path]:
    files = [
        root / name
        for name in (
            "app.py",
            "desktop.py",
            "desktop.spec",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "requirements.txt",
            "requirements.lock",
            "requirements-dev.lock",
            "requirements-demo.lock",
            "requirements-desktop-build.lock",
            "uv.lock",
            "pyproject.toml",
            "Dockerfile",
            "compose.yaml",
            ".dockerignore",
            ".gitignore",
            ".gitattributes",
            ".env.example",
            ".streamlit/config.toml",
            ".github/workflows/ci.yml",
            ".github/workflows/windows-client.yml",
        )
    ]
    patterns = {
        "src": ("*.py",),
        "data": ("*.md", "*.xlsx", "*.json"),
        "docs": ("*.md", "*.json"),
        "tests": ("*.py",),
        "scripts": ("*.py",),
        "screenshots": ("*.png", "*.md"),
        "media": ("*.mp4", "*.md"),
    }
    for folder, globs in patterns.items():
        for pattern in globs:
            files.extend((root / folder).glob(pattern))
    return sorted(set(path for path in files if path.is_file()))


def main() -> None:
    # Imported here to avoid the shared allowlist helper's circular import.
    from scripts.check_delivery import check_delivery

    check_delivery(ROOT)
    destination = ROOT / "dist" / bundle_name()
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in release_files(ROOT):
            archive.write(path, "ai-business-solution-agent/" + path.relative_to(ROOT).as_posix())
    print(f"Release bundle: {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
