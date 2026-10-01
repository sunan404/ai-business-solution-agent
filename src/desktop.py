"""Local desktop lifecycle. No client material or API keys are written to logs."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from dotenv import load_dotenv

from .version import project_version

APP_NAME = "AI 商业需求诊断助手"


def resource_root() -> Path:
    return Path(__file__).resolve().parents[1]


def user_directory() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return base / "BusinessDiagnosis"


def prepare_environment(folder: Path) -> Path:
    """Keep mutable state outside the installation; system variables win over .env."""
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / ".env"
    try:
        with config.open("x", encoding="utf-8") as handle:
            handle.write((resource_root() / ".env.example").read_text(encoding="utf-8"))
    except FileExistsError:
        pass
    load_dotenv(config, override=False)
    os.environ["DIAGNOSIS_DESKTOP"] = "1"
    os.environ["DIAGNOSIS_CONFIG_PATH"] = str(config)
    quota = Path(os.getenv("QUOTA_DB_PATH", "runtime/quota.sqlite3"))
    if not quota.is_absolute():
        quota = folder / quota
    os.environ["QUOTA_DB_PATH"] = str(quota)
    return config


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def server_command(port: int, startup_status: Path | None = None) -> list[str]:
    args = ["--serve", "--port", str(port), "--parent-pid", str(os.getpid())]
    if startup_status is not None:
        args += ["--startup-status", str(startup_status)]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(resource_root() / "desktop.py"), *args]


class LocalServer:
    def __init__(self) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process: subprocess.Popen | None = None
        self.startup_directory: TemporaryDirectory | None = None

    def start(self, timeout: float = 60) -> None:
        self.startup_directory = TemporaryDirectory(prefix="diagnosis-start-")
        startup_status = Path(self.startup_directory.name) / "status.json"
        self.process = subprocess.Popen(
            server_command(self.port, startup_status),
            cwd=resource_root(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                if startup_status.exists():
                    info = json.loads(startup_status.read_text(encoding="utf-8"))
                    raise RuntimeError(
                        "本地服务未能启动："
                        + info["error_type"]
                        + (f"（缺少模块 {info['missing_module']}）" if info.get("missing_module") else "")
                    )
                raise RuntimeError("本地服务未能启动，请检查配置文件中的模型、预算与访问设置。")
            try:
                with opener.open(self.url + "/_stcore/health", timeout=1) as response:
                    if response.status == 200 and response.read() == b"ok":
                        return
            except (URLError, OSError):
                pass
            time.sleep(0.15)
        raise RuntimeError("本地服务启动超时，请关闭客户端后重试。")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if sys.platform == "win32":
                # A venv's python.exe can be a redirector with a separate interpreter child.
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10,
                    check=False,
                )
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.startup_directory is not None:
            self.startup_directory.cleanup()

    def __enter__(self) -> LocalServer:
        try:
            self.start()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


def _watch_parent(parent_pid: int) -> None:
    """A killed desktop must not leave its backend running on Windows."""
    if sys.platform != "win32":
        return
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE only
    if not handle:
        os._exit(1)
    try:
        if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
            os._exit(0)
    finally:
        kernel.CloseHandle(handle)


def serve(port: int, parent_pid: int) -> None:
    from streamlit.web import bootstrap

    from .start import validate_deployment

    validate_deployment()
    threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()
    flags = {
        "global_developmentMode": False,
        "server_address": "127.0.0.1",
        "server_port": port,
        "server_headless": True,
        "server_fileWatcherType": "none",
        "server_enableCORS": True,
        "server_enableXsrfProtection": True,
        "browser_gatherUsageStats": False,
        "client_toolbarMode": "minimal",
    }
    bootstrap.load_config_options(flags)
    bootstrap.run(
        str(resource_root() / "app.py"),
        False,
        [],
        flags,
    )


def smoke_test(destination: Path) -> None:
    """Exercise installed resources, both report pages, HTTP and backend shutdown."""
    from streamlit.testing.v1 import AppTest

    from .diagnose import diagnose
    from .ingest import read_demo_text, read_uploaded_file
    from .report import render_markdown

    root = resource_root()
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "APP_ACCESS_PASSWORD"):
        os.environ[key] = ""
    os.environ["APP_ENV"] = "development"
    os.environ["LLM_PROVIDER"] = "openai"
    with TemporaryDirectory(prefix="diagnosis-smoke-") as temporary:
        os.environ["QUOTA_DB_PATH"] = str(Path(temporary) / "runtime" / "quota.sqlite3")
        config = prepare_environment(Path(temporary))
        if config.parent != Path(temporary):
            raise RuntimeError("Smoke configuration escaped its temporary directory")
        for name in ("demo_game_publisher.md", "demo_consumer_brand.md"):
            report = diagnose(read_demo_text(root / "data" / name), name)
            if not report["pain_points"] or "证据摘录" not in render_markdown(report):
                raise RuntimeError("Bundled text example did not generate a report")
        workbook = root / "data" / "demo_consumer_brand.xlsx"
        if "原始访谈摘录" not in read_uploaded_file(workbook.name, workbook.read_bytes()):
            raise RuntimeError("Bundled XLSX did not parse")
        app = AppTest.from_file(str(root / "app.py")).run(timeout=30)
        app.button[0].click().run(timeout=30)
        if app.exception or not app.get("download_button"):
            raise RuntimeError("Game report page or download failed")
        app.selectbox[0].select("消费品牌团队").run(timeout=30)
        app.button[0].click().run(timeout=30)
        if app.exception or not app.get("download_button"):
            raise RuntimeError("Brand report page or download failed")
        with LocalServer() as server:
            opener = build_opener(ProxyHandler({}))
            with opener.open(server.url, timeout=5) as response:
                if response.status != 200 or b"<html" not in response.read().lower():
                    raise RuntimeError("HTTP app shell did not load")
        if server.process is None or server.process.poll() is None:
            raise RuntimeError("Backend was left running")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "passed": True,
                "version": project_version(),
                "frozen": bool(getattr(sys, "frozen", False)),
                "checks": [
                    "text_examples",
                    "xlsx",
                    "both_report_pages",
                    "download_buttons",
                    "http",
                    "shutdown",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def gui_smoke_test(destination: Path) -> None:
    """Verify the actual embedded WebView2 UI in a hidden native window."""
    import webview
    from webview.platforms.edgechromium import EdgeChrome

    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "APP_ACCESS_PASSWORD"):
        os.environ[key] = ""
    os.environ["APP_ENV"] = "development"
    os.environ["LLM_PROVIDER"] = "openai"
    result: dict = {"passed": False}
    with TemporaryDirectory(prefix="diagnosis-gui-") as temporary:
        os.environ["QUOTA_DB_PATH"] = str(Path(temporary) / "quota.sqlite3")
        prepare_environment(Path(temporary))
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        download = Path(temporary) / "report.md"
        original_download_handler = EdgeChrome.on_download_starting

        def save_test_download(self: object, sender: object, args: object) -> None:
            # Same native download event, with its modal destination picker automated for QA only.
            args.ResultFilePath = str(download)
            args.Handled = True

        EdgeChrome.on_download_starting = save_test_download
        with LocalServer() as server:
            window = webview.create_window(APP_NAME, server.url, hidden=True, width=1360, height=900)

            def check_ui() -> None:
                try:
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        ready = window.evaluate_js(
                            "Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('生成结构化诊断报告'))"
                        )
                        if ready:
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebView2 did not load the application")
                    window.evaluate_js(
                        "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('生成结构化诊断报告')).click()"
                    )
                    while time.monotonic() < deadline:
                        ready = window.evaluate_js(
                            "document.body.innerText.includes('客户诊断报告｜游戏发行团队') && document.body.innerText.includes('下载 Markdown 诊断报告')"
                        )
                        if ready:
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebView2 report or download button did not render")
                    window.evaluate_js(
                        "Array.from(document.querySelectorAll('[data-testid=stRadio] label')).find(l => l.textContent.includes('上传文件')).click()"
                    )
                    while time.monotonic() < deadline:
                        if window.evaluate_js("Boolean(document.querySelector('input[type=file]'))"):
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebView2 file upload control did not render")
                    window.evaluate_js(
                        "(() => {const input = document.querySelector('input[type=file]');"
                        "const transfer = new DataTransfer();"
                        "transfer.items.add(new File(['市场团队希望本月完成渠道验证。当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。'], 'gui-input.txt', {type:'text/plain'}));"
                        "input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles:true}));})()"
                    )
                    while time.monotonic() < deadline:
                        if window.evaluate_js("document.body.innerText.includes('已读取 gui-input.txt')"):
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebView2 upload did not reach the application")
                    window.evaluate_js(
                        "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('生成结构化诊断报告')).click()"
                    )
                    while time.monotonic() < deadline:
                        if window.evaluate_js(
                            "document.body.innerText.includes('客户诊断报告｜gui-input.txt')"
                        ):
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("Uploaded material did not generate a native report")
                    window.evaluate_js(
                        "document.querySelector('[data-testid=stDownloadButton] button').click()"
                    )
                    while time.monotonic() < deadline:
                        if download.exists() and "证据摘录" in download.read_text(encoding="utf-8"):
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("Native report download did not save its contents")
                    result.update(
                        {
                            "passed": True,
                            "version": project_version(),
                            "frozen": bool(getattr(sys, "frozen", False)),
                            "engine": "edgechromium",
                            "checks": [
                                "native_window",
                                "report_generation",
                                "download_control",
                                "upload_control",
                                "file_upload",
                                "uploaded_report",
                                "native_download",
                            ],
                        }
                    )
                except Exception as exc:
                    result["error_type"] = type(exc).__name__
                    result["check_error"] = str(exc)
                finally:
                    window.destroy()

            try:
                webview.start(check_ui, gui="edgechromium", private_mode=True)
            finally:
                EdgeChrome.on_download_starting = original_download_handler
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["passed"]:
        raise RuntimeError("Native window smoke test failed")


def launch() -> None:
    import webview
    from webview.menu import Menu, MenuAction

    config = prepare_environment(user_directory())
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["ALLOW_FILE_URLS"] = False
    with LocalServer() as server:
        webview.create_window(
            f"{APP_NAME} · v{project_version()}",
            server.url,
            width=1360,
            height=900,
            min_size=(960, 640),
            text_select=True,
        )
        menu = [
            Menu(
                "设置",
                [
                    MenuAction("编辑模型配置（保存后重启）", lambda: os.startfile(config)),
                    MenuAction("打开配置目录", lambda: os.startfile(config.parent)),
                ],
            )
        ]
        webview.start(gui="edgechromium", private_mode=True, menu=menu)


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--startup-status", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", type=Path, metavar="RESULT_JSON")
    parser.add_argument("--gui-smoke-test", type=Path, metavar="RESULT_JSON")
    options = parser.parse_args(argv)
    # Windowed frozen applications do not have stdout/stderr handles.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    try:
        if options.serve:
            if not options.port or not options.parent_pid:
                parser.error("Internal server requires a port and parent PID")
            serve(options.port, options.parent_pid)
        elif options.smoke_test:
            smoke_test(options.smoke_test)
        elif options.gui_smoke_test:
            gui_smoke_test(options.gui_smoke_test)
        else:
            launch()
    except Exception as exc:
        if options.smoke_test or options.gui_smoke_test:
            destination = options.smoke_test or options.gui_smoke_test
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not options.gui_smoke_test or not destination.exists():
                destination.write_text(
                    json.dumps({"passed": False, "error_type": type(exc).__name__, "check_error": str(exc)}),
                    encoding="utf-8",
                )
        elif options.serve and options.startup_status:
            options.startup_status.write_text(
                json.dumps({"error_type": type(exc).__name__, "missing_module": getattr(exc, "name", None)}),
                encoding="utf-8",
            )
        elif not options.serve:
            message = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else (
                    "客户端未能启动。请确认已安装 Microsoft Edge WebView2 Runtime，"
                    "并将 ZIP 完整解压到本地目录。\n"
                    f"错误类型：{type(exc).__name__}"
                )
            )
            _show_error(message)
        return 1
    return 0
