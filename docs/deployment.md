# 部署与运维

## 交付范围与启动

正式分发使用 `python -m scripts.package_release` 生成的白名单 ZIP，解压后按 README 运行。Python wheel 只包含核心库，不是完整的 Streamlit 服务分发物。

Docker/Compose 面向单实例受控试点，默认 loopback 端口；映射公网前必须配置反向代理 HTTPS、请求频率/连接数限制与访问记录。共享口令仅适合少量授权试用者，不是多租户或企业 SSO。

`.env` 模板的 API Key、访问口令与真实运营方信息只能在部署环境填写。`APP_ENV=production` 时，启动检查要求 12 位以上口令、运营方和联系方式；不满足时退出，不以健康页冒充完整可用服务。直接运行 `streamlit` 也会在页面关闭诊断入口。

```bash
docker compose up --build -d
docker compose logs -f app
curl --fail http://127.0.0.1:8501/_stcore/health
```

健康端点验证 HTTP 进程，不能单独证明模型、上传、权限与报告路径都正常。验收应登录、读取两个案例、核验生成与下载，并经授权用虚构案例进行真实模型联调。

## 预算与费用

所有实际模型调用先向同一个 SQLite 数据库原子预留。每日尝试次数含最坏重试数；token 预留按输入 UTF-8 字节估算加协议余量、每次输出上限，再乘尝试次数。调用失败不归还，避免重复试错绕过额度。

日期按 Asia/Hong_Kong。Compose 挂载 `quota` volume，刷新页面、重启进程和重建容器不会重置它。**不能删除 volume 来运维重启；多实例必须改为共享中央配额服务，不能各自用独立 SQLite。** 文件无法读写时停止请求，不能降级为无限制调用。

`LLM_DAILY_USD_BUDGET=0` 表示金额预算未启用，仍有请求和 token 限额。启用金额预算必须填写输入、输出每百万 token 的实际美元费率；改模型后同步更新。展示费用是估算，忽略缓存优惠，也无法完整知道失败/重试中的计费用量。服务商账单和费用限制是最终保障。

SDK 重试仅适用于其网络/状态码规则；单次超时默认 30 秒、重试默认 1 次，总时间可能超过 60 秒。不得将输入/输出限制包装为模型响应速度 SLA。

默认日预算 2,000,000 token 预留、20 次尝试预留、输出上限 6,000。它们是同时生效的上限而非保证次数，中文大文件会先用尽 token 预算。生产启动校验最大请求是否可容纳；单次超过整日预算与当日已用尽分别提示。`TENANT_ID` 从服务端环境配置，`TENANT_DAILY_REQUEST_LIMIT` / `TENANT_DAILY_TOKEN_BUDGET` 设置独立限额；全局限额仍同时生效。SQLite 保留旧全局记录，不把旧记录伪分配给某客户。返回用量按日期、租户累计，失败校验的返回用量也记录；这不提供完整租户认证、数据隔离或商业计费。

OpenAI 使用 `OPENAI_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`，由 `LLM_PROVIDER` 选择。公共 API 的模型名与权限可能变化，部署前核验账户可用型号。DeepSeek JSON 模式不等于服务器强制 schema，应用仍严格拒绝字段、等级或证据不合格的输出。

登录页面的 3 秒等待只是会话冷却，没有服务端/IP 尝试计数，可被新会话绕过；不能当成防爆破限流。公网前必须配置反向代理限流或替换为合适的身份系统。

## 可复现依赖

运行安装 `pip install --require-hashes -r requirements.lock`，测试安装 `requirements-dev.lock`，录屏安装 `requirements-demo.lock`。`uv.lock` 是统一解析记录；修改 pyproject 后使用 uv lock 和 uv export 重新生成相应 hash 锁文件。生产镜像只装运行依赖，不包含 pytest，基础镜像按 digest 固定。不要用浮动版本安装后宣称与已验证镜像一致。

## 日志与排错

JSON 日志到标准错误输出，含事件名、随机诊断编号、错误类别、耗时、返回 token 和估算费用；不含客户原文、文件名、访问口令、API Key 或底层异常正文。页面给出编号前 12 位，可在日志搜索相同前缀。

事件：`llm_started`、`llm_usage`、`llm_completed`、`llm_failed`、`llm_blocked`。分类：authentication、permission、model_not_found、rate_limit、connection、bad_request、output_validation、provider_or_internal、quota。未知异常仅补充 Python 异常类型名，不记录异常正文。

管理员应限制日志权限与保存期，按合同设置轮转。不要在客户环境开启 SDK HTTP body 调试，不把含客户资料的报错截图贴到公开 Issues。日志是基础诊断能力，尚无自动告警平台。

## 发布前核对

1. 运行测试、Ruff、Mypy、规则评估；核验 ZIP 和镜像上下文不含密钥与缓存。
2. 阅读隐私、条款和处理草案，填写实际身份、联系人、部署位置、日志期限、服务商与数据删除流程。
3. 用未登录页面验证访问门；用异常输入验证拒绝；用测试额度验证共享配额；核对两种模式下载。
4. 真实模型联调记录模型名、日期、token、失败类别与人工评价，不虚构未测指标。
5. 配置服务商费用限制、反向代理 TLS/限速，备份仅非敏感配置与预算；事件发生时暂停模型入口并轮换凭据。

## 当前验证边界

本地测试与浏览器演示可在无 API Key 情况下验证。当前工作环境未安装 Docker，因此不声称镜像已经本地构建通过；CI 提供构建与容器 smoke 检查，需发布后核验实际 Actions 结果。政策材料未经律师审查，也没有真实客户合同验收记录。
