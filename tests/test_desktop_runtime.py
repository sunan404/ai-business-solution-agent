import hashlib
from pathlib import Path

import pytest

from src.desktop_runtime import unblock_bundled_assemblies


def test_only_verified_bundled_library_is_unblocked(tmp_path):
    library = tmp_path / "Python.Runtime.dll"
    library.write_bytes(b"release library")
    marker = Path(str(library) + ":Zone.Identifier")
    marker.write_text("[ZoneTransfer]\nZoneId=3\n", encoding="utf-8")
    unrelated = tmp_path / "customer.txt"
    unrelated.write_text("customer file", encoding="utf-8")
    unrelated_marker = Path(str(unrelated) + ":Zone.Identifier")
    unrelated_marker.write_text("[ZoneTransfer]\nZoneId=3\n", encoding="utf-8")
    unblock_bundled_assemblies(tmp_path, {library.name: hashlib.sha256(library.read_bytes()).hexdigest()})
    assert not marker.exists()
    assert unrelated_marker.exists()
    assert library.read_bytes() == b"release library"
    # Repeated launches also succeed once the marker has been removed.
    unblock_bundled_assemblies(tmp_path, {library.name: hashlib.sha256(library.read_bytes()).hexdigest()})


def test_changed_library_is_rejected_without_unblocking(tmp_path):
    library = tmp_path / "Python.Runtime.dll"
    library.write_bytes(b"changed library")
    marker = Path(str(library) + ":Zone.Identifier")
    marker.write_text("[ZoneTransfer]\nZoneId=3\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="组件校验失败"):
        unblock_bundled_assemblies(tmp_path, {library.name: hashlib.sha256(b"release library").hexdigest()})
    assert marker.exists()


@pytest.mark.parametrize("relative", ["../outside.dll", "customer.txt"])
def test_unblocking_cannot_escape_bundled_libraries(tmp_path, relative):
    with pytest.raises(RuntimeError, match="组件清单无效"):
        unblock_bundled_assemblies(tmp_path, {relative: "0" * 64})


def test_normal_entrypoint_prepares_runtime_before_loading_window(monkeypatch):
    from src import desktop

    calls = []
    monkeypatch.setattr(desktop, "prepare_windows_runtime", lambda root: calls.append("runtime"))
    monkeypatch.setattr(desktop, "launch", lambda: calls.append("window"))
    assert desktop.main([]) == 0
    assert calls == ["runtime", "window"]
