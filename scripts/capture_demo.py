"""Capture actual browser screenshots and a silent 120-second local-mode walkthrough."""

import argparse
import asyncio
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def capture(url: str, duration: int) -> None:
    shots = ROOT / "screenshots"
    media = ROOT / "media"
    shots.mkdir(exist_ok=True)
    media.mkdir(exist_ok=True)
    raw = media / "raw"
    raw.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            record_video_dir=str(raw),
            record_video_size={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()
        await page.goto(url)
        await page.get_by_role("button", name="生成结构化诊断报告", exact=True).wait_for()

        async def caption(text: str, fraction: float) -> None:
            await page.evaluate(
                """text => {
                let el = document.getElementById('recording-caption');
                if (!el) { el = document.createElement('div'); el.id='recording-caption'; document.body.appendChild(el); }
                el.textContent=text;
                el.style.cssText='position:fixed;bottom:12px;left:380px;right:22px;z-index:999999;background:#132e48;color:white;border-radius:8px;padding:14px;font:18px sans-serif;box-shadow:0 2px 12px #0003;pointer-events:none';
            }""",
                text,
            )
            await asyncio.sleep(duration * fraction)

        async def screenshot(name: str) -> None:
            await page.evaluate("document.getElementById('recording-caption')?.remove()")
            await page.screenshot(path=str(shots / name))

        async def align(locator) -> None:
            await locator.evaluate("""el => {
                el.scrollIntoView({block: 'start'});
                document.querySelector('[data-testid="stMain"]')?.scrollBy(0, -90);
            }""")

        await screenshot("01-home.png")
        await caption("AI 商业需求诊断助手｜真实页面自动录屏 · 虚构资料 · 本地规则模式", 0.125)
        await page.get_by_role("button", name="生成结构化诊断报告", exact=True).click()
        title = page.get_by_text("客户诊断报告｜游戏发行团队", exact=True)
        await title.wait_for()
        await align(title)
        await screenshot("02-game-report.png")
        await caption("游戏发行：从原文识别目标、角色与工具，每项结论附证据摘录。", 0.20)
        pain_title = page.get_by_text("痛点优先级与解决思路", exact=True)
        await align(pain_title)
        await caption("统一计算影响×2＋紧迫度；缺少信息则待确认，建议需人工核验。", 0.20)
        await page.get_by_role("combobox").click()
        await page.get_by_role("option", name="消费品牌团队", exact=True).click()
        await page.get_by_role("button", name="生成结构化诊断报告", exact=True).click()
        brand = page.get_by_text("客户诊断报告｜消费品牌团队", exact=True)
        await brand.wait_for()
        await align(brand)
        await screenshot("03-brand-report.png")
        await caption("消费品牌：完整访谈与 Excel 联合输入，聚焦渠道交接、活动排期与数据口径。", 0.20)
        download_button = page.get_by_role("button", name="下载 Markdown 诊断报告", exact=True)
        await download_button.scroll_into_view_if_needed()
        async with page.expect_download() as download_info:
            await download_button.click()
        downloaded = await download_info.value
        if await downloaded.failure():
            raise RuntimeError("Report download failed")
        await screenshot("04-download.png")
        await caption("报告可下载并保留证据与待确认问题；配套指南说明四周试点与验收参考。", 0.15)
        await page.get_by_text("LLM 增强模式", exact=True).click()
        await page.get_by_text("API Key 配置指南", exact=True).click()
        await caption(
            "可选 LLM：环境密钥、外发确认、访问口令、共享配额和输出校验。本视频未调用真实 API。", 0.125
        )
        video = page.video
        await context.close()
        assert video is not None
        source = await video.path()
        await browser.close()
    # Trim to exactly 120 seconds (or supplied duration); do not synthesize app output.
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            str(source),
            "-t",
            str(duration),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(media / "demo-local.mp4"),
        ],
        check=True,
        capture_output=True,
    )
    print("Captured four screenshots and media/demo-local.mp4 (silent automated browser walkthrough).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8502")
    parser.add_argument("--duration", type=int, default=120)
    arguments = parser.parse_args()
    asyncio.run(capture(arguments.url, arguments.duration))
