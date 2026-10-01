"""Prepare only verified, bundled DLLs before initializing the Windows CLR."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def unblock_bundled_assemblies(root: Path, assemblies: dict[str, str]) -> None:
    """Downloaded ZIPs propagate Zone.Identifier to managed assemblies on NTFS."""
    root = root.resolve()
    for relative, expected in assemblies.items():
        library = (root / relative).resolve()
        if not library.is_relative_to(root) or library.suffix.lower() != ".dll":
            raise RuntimeError("客户端组件清单无效，请重新下载并完整解压客户端。")
        marker = Path(str(library) + ":Zone.Identifier")
        if not marker.exists():
            continue
        if not library.is_file() or hashlib.sha256(library.read_bytes()).hexdigest() != expected:
            raise RuntimeError("客户端组件校验失败，请从 GitHub 重新下载并完整解压客户端。")
        try:
            marker.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(
                "Windows 锁定了下载的客户端组件。请在下载 ZIP 的属性中勾选“解除锁定”，"
                "再将整个 ZIP 解压到有写入权限的本地目录。"
            ) from exc


def prepare_windows_runtime(root: Path) -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    # Embedded in the executable by desktop.spec, never read from a mutable JSON file.
    from desktop_assembly_manifest import ASSEMBLIES

    unblock_bundled_assemblies(root, ASSEMBLIES)
