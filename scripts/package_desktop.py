"""Package only a clean frozen client and public instructions; add SHA-256."""

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.version import project_version

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    folder = ROOT / "dist" / "BusinessDiagnosis"
    if not (folder / "BusinessDiagnosis.exe").is_file():
        raise SystemExit("Build desktop.spec before packaging the Windows client.")
    destination = ROOT / "dist" / f"BusinessDiagnosis-{project_version()}-windows-x64.zip"
    files = [path for path in folder.rglob("*") if path.is_file()]
    forbidden = {".env", "secrets.toml", "quota.sqlite3"}
    for path in files:
        if path.name in forbidden or path.suffix in {".log", ".sqlite3", ".db"}:
            raise SystemExit(f"Refusing to package mutable or secret file: {path.name}")
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, "BusinessDiagnosis/" + path.relative_to(folder).as_posix())
        archive.write(ROOT / "docs" / "desktop.md", "BusinessDiagnosis/使用说明.md")
        archive.write(ROOT / "LICENSE", "BusinessDiagnosis/LICENSE")
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
    print(f"Windows client: {destination.name}, {destination.stat().st_size:,} bytes")
    print(f"SHA-256: {checksum}")


if __name__ == "__main__":
    main()
