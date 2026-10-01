# Build with: python -m PyInstaller --noconfirm desktop.spec
from pathlib import Path
import hashlib
import importlib.util

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH)
# Trusted hashes live in the executable's PYZ archive. Only matching bundled DLLs
# may have their inherited Internet-zone marker removed before .NET initializes.
manifest_folder = root / "build" / "desktop-manifest"
manifest_folder.mkdir(parents=True, exist_ok=True)
assemblies = {}
for package in ("pythonnet", "clr_loader", "webview"):
    package_root = Path(importlib.util.find_spec(package).origin).parent
    for library in sorted(package_root.rglob("*.dll")):
        relative = package + "/" + library.relative_to(package_root).as_posix()
        assemblies[relative] = hashlib.sha256(library.read_bytes()).hexdigest()
(manifest_folder / "desktop_assembly_manifest.py").write_text(
    "ASSEMBLIES = " + repr(assemblies) + "\n", encoding="utf-8"
)
streamlit_data, streamlit_binaries, streamlit_imports = collect_all("streamlit")
datas = streamlit_data + copy_metadata("streamlit", recursive=True) + copy_metadata("pywebview", recursive=True)
datas += [(str(root / name), ".") for name in ("app.py", "pyproject.toml", ".env.example")]
for folder, patterns in {
    "src": ("*.py",),
    "data": ("*.md", "*.xlsx"),
    "docs": ("privacy.md", "terms.md", "data-processing.md"),
    ".streamlit": ("config.toml",),
}.items():
    for pattern in patterns:
        datas += [(str(path), folder) for path in (root / folder).glob(pattern)]

a = Analysis(
    [str(root / "desktop.py")],
    pathex=[str(root), str(manifest_folder)],
    binaries=streamlit_binaries,
    datas=datas,
    hiddenimports=streamlit_imports + collect_submodules("src") + ["webview.platforms.edgechromium", "desktop_assembly_manifest"],
    excludes=["pytest", "mypy", "ruff", "playwright", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="BusinessDiagnosis", console=False, debug=False, strip=False, upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BusinessDiagnosis")
