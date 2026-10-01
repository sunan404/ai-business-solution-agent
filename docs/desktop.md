# Windows 桌面客户端

版本：0.3.1 · Windows 10/11 x64。

## 下载与启动

1. 打开 [GitHub Releases](https://github.com/sunan404/ai-business-solution-agent/releases)，下载 `BusinessDiagnosis-0.3.1-windows-x64.zip`。
2. 将整个 ZIP 解压到本地目录，保留 `BusinessDiagnosis.exe` 旁的 `_internal` 文件夹。
3. 双击 `BusinessDiagnosis.exe`，等待本地服务启动，进入独立窗口。
4. 选择内置案例、粘贴资料或上传 TXT / Markdown / CSV / XLSX，生成并下载报告。

客户端已包含 Python 和应用依赖，不需要安装 Python、Node.js 或启动命令行。使用系统的 Microsoft Edge WebView2 Runtime；如果启动提示缺少运行时，请通过 [微软官方页面](https://developer.microsoft.com/microsoft-edge/webview2/) 安装 Evergreen Runtime 后重试。

客户端首次启动会校验内置 DLL 的 SHA-256，仅对与构建时一致的客户端组件解除下载后继承的网络标记，以避免 .NET 拒绝加载。不会处理你的上传资料、配置或其他目录。若解压目录不可写，请先右键下载的 ZIP → 属性 → 解除锁定，再完整解压到个人有写入权限的目录。

此版本提供便携 ZIP，尚未使用代码签名证书；Windows 可能提示未知发布者。发布页提供 `.sha256` 校验文件，可以用 `Get-FileHash` 核对完整性。

## 本地与模型模式

本地规则模式无需密钥，无需连接模型服务。LLM 模式仍需自己的 OpenAI 或 DeepSeek API Key，并可能产生服务商费用；选择模型模式后还需在页面确认本次资料外发。

窗口顶部的“设置 → 编辑模型配置（保存后重启）”打开配置文件。首次启动自动从空密钥模板创建配置；默认路径为：

```text
%LOCALAPPDATA%\BusinessDiagnosis\.env
```

按模板填写 `LLM_PROVIDER` 和对应密钥、模型名，保存并关闭所有客户端窗口，再重新启动。已有系统环境变量优先于配置文件。密钥保存于本机文本配置中，应用不把它上传到 GitHub；不要把配置文件分享给其他人。

默认共享预算数据库位于 `%LOCALAPPDATA%\BusinessDiagnosis\runtime\quota.sqlite3`。同一 Windows 用户启动多个窗口时共享每日预算；系统环境变量中的绝对 `QUOTA_DB_PATH` 可覆盖位置。更新或移动解压目录不会重置配置和预算。

## 窗口和数据

本地服务只监听 `127.0.0.1` 的随机端口，客户端窗口关闭后停止服务。Windows 上即使主窗口进程意外终止，后台也会检测父进程退出并停止。无需打开浏览器或手工结束后台进程。

报告下载使用 WebView2 的保存对话框。窗口使用私密浏览模式，不保留页面会话；上传资料仅在运行内存中处理，下载副本由你管理。配置和预算留在上述用户目录，详见[隐私说明](privacy.md)。

## 从源码运行和构建

推荐 Windows x64、Python 3.12。在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-desktop-build.lock
.\.venv\Scripts\python.exe desktop.py
```

打包和验证：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm desktop.spec
$client = Start-Process -FilePath .\dist\BusinessDiagnosis\BusinessDiagnosis.exe -ArgumentList '--smoke-test', 'smoke.json' -WindowStyle Hidden -Wait -PassThru
if ($client.ExitCode -ne 0) { throw 'Client smoke test failed' }
Get-Content .\smoke.json
.\.venv\Scripts\python.exe -m scripts.package_desktop
```

源码和客户端有不同分发包：`ai-business-solution-agent-0.3.1.zip` 是源码服务包，`BusinessDiagnosis-0.3.1-windows-x64.zip` 是可直接启动的 Windows 客户端。

构建依赖由 `pyproject.toml` 与 `uv.lock` 管理，锁文件导出方式：

```powershell
uv lock
uv export --frozen --no-dev --no-emit-project --extra desktop --extra desktop-build --output-file requirements-desktop-build.lock
```
