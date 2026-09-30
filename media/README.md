# 演示视频

`demo-local.mp4` 为真实 Streamlit 页面录制的 2 分钟静音演示，使用 Playwright 自动操作并添加中文讲解字幕。全程使用虚构案例与本地规则，没有演出真实 LLM 调用或商业结果。字幕是视频制作叠层，不属于产品界面。

可用 `python -m scripts.capture_demo` 重录，需安装 `pip install -e ".[demo]"` 和 `python -m playwright install chromium`，并在 8502 端口启动本地应用。发布平台若不能内嵌播放，可下载 MP4 或放入 GitHub Release；仓库中的文件链接不冒充在线托管播放器。
