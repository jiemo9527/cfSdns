from __future__ import annotations

import asyncio
import json
import logging
import os
import platform

from playwright.async_api import async_playwright

from .logging_utils import configure_logging


logger = logging.getLogger(__name__)
ITDOG_URL = "https://www.itdog.cn/http/"
CESU_URL = "https://www.cesu.ai/http_batch"
PLAYWRIGHT_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--window-size=1920,1080",
]
PLAYWRIGHT_IGNORE_ARGS = ["--enable-automation"]
PLAYWRIGHT_VIEWPORT = {"width": 1920, "height": 1080}
ANTI_BOT_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


def _get_user_data_dir(dirname: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, dirname)


async def _launch_persistent_context(playwright, user_data_dir: str):
    logger.info("启动浏览器上下文: system=%s user_data_dir=%s", platform.system(), user_data_dir)
    return await playwright.chromium.launch_persistent_context(
        user_data_dir,
        headless=True,
        args=PLAYWRIGHT_LAUNCH_ARGS,
        ignore_default_args=PLAYWRIGHT_IGNORE_ARGS,
        viewport=PLAYWRIGHT_VIEWPORT,
    )


async def _save_debug_screenshot(page, screenshot_path: str, label: str) -> None:
    if page is None:
        return

    try:
        await page.screenshot(path=screenshot_path)
        logger.info("已保存 %s 失败截图: %s", label, screenshot_path)
    except Exception as exc:
        logger.warning("保存 %s 截图失败: path=%s error=%s", label, screenshot_path, exc)


def _register_itdog_finish_listener(page, test_finished_event: asyncio.Event) -> None:
    def handle_ws_message(ws):
        def process_payload(payload_str):
            if not isinstance(payload_str, str):
                return

            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                return

            if data.get("type") == "finished":
                logger.info("IT-Dog 检测完成信号已收到。")
                test_finished_event.set()

        ws.on("framereceived", process_payload)

    page.on("websocket", handle_ws_message)


def _register_cesu_finish_listener(page, test_finished_event: asyncio.Event, num_urls: int) -> None:
    finish_count = 0

    def handle_ws_message(ws):
        nonlocal finish_count

        def process_payload(payload_str):
            nonlocal finish_count
            if not isinstance(payload_str, str):
                return

            try:
                data = json.loads(payload_str)
            except (json.JSONDecodeError, TypeError):
                return

            if isinstance(data, dict) and data.get("message") == "finish":
                finish_count += 1
                logger.info("CESU 进度: %s/%s", finish_count, num_urls)
                if finish_count >= num_urls:
                    logger.info("CESU 所有任务完成。")
                    test_finished_event.set()

        ws.on("framereceived", process_payload)

    page.on("websocket", handle_ws_message)


async def _extract_itdog_results(page) -> str | None:
    logger.info("开始提取 IT-Dog 结果表格...")
    await page.wait_for_timeout(1000)
    results = await page.evaluate(r'''() => {
        const table = document.querySelector("#simpletable");
        if (!table) return null;
        const unwanted = ['Head', '赞助商广告'];
        const headers = Array.from(table.querySelectorAll("thead th"))
                             .map((th, index) => ({ text: th.innerText.trim(), index }))
                             .filter(h => !unwanted.includes(h.text));
        const rows = Array.from(table.querySelectorAll("tbody tr.node_tr"));
        return rows.map(row => {
            const cells = Array.from(row.querySelectorAll("td"));
            const rowData = {};
            headers.forEach(h => {
                rowData[h.text] = cells[h.index] ? cells[h.index].innerText.trim().replace(/\s+/g, ' ') : '';
            });
            return rowData;
        });
    }''')

    if not results:
        logger.warning("未找到 IT-Dog 结果表格。")
        return None

    return json.dumps(results, indent=2, ensure_ascii=False)


async def _extract_cesu_results(page) -> str | None:
    logger.info("开始提取 CESU 结果表格...")
    await page.wait_for_timeout(2500)
    results = await page.evaluate(r'''() => {
        const table = document.querySelector("table.table.table_cont");
        if (!table) return null;
        const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.innerText.trim());
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        return rows.map(row => {
            const cells = Array.from(row.querySelectorAll("td"));
            const rowData = {};
            headers.forEach((header, index) => {
                const cell = cells[index];
                if (!cell) { rowData[header] = ''; return; }
                const cellText = cell.innerText.trim();
                if (!['序号', '检测目标', '异常节点(占比)', '操作'].includes(header)) {
                    const parts = cellText.split('\n');
                    const timeAndStatus = parts[0].trim();
                    let status = '', time = '', ip = '', ipLocation = '';
                    if (isNaN(parseInt(timeAndStatus, 10))) {
                        status = timeAndStatus; time = '--';
                    } else {
                        status = timeAndStatus.substring(0, 3); time = timeAndStatus.substring(3);
                    }
                    if (parts.length > 1) {
                        const ipInfo = parts.slice(1).join(' ').trim();
                        const match = ipInfo.match(/^[\d\.:a-fA-F]+\s*\[.*\]$/)
                            ? ipInfo.match(/^([\d\.:a-fA-F]+)\s*\[(.*)\]$/)
                            : [null, ipInfo, ''];
                        if (match) { ip = match[1] || ipInfo; ipLocation = match[2] || ''; }
                    }
                    rowData[header] = { '状态': status, '耗时': time, 'IP': ip, 'IP归属地': ipLocation };
                } else {
                    rowData[header] = cellText;
                }
            });
            return rowData;
        });
    }''')

    if not results:
        logger.warning("未能找到 CESU 结果表格 table.table.table_cont。")
        return None

    return json.dumps(results, indent=2, ensure_ascii=False)


async def run_itdog_test(target_host: str, custom_dns: str):
    """执行 IT-Dog 自动测速。"""
    user_data_dir = _get_user_data_dir("itdog_userdata")
    test_finished_event = asyncio.Event()
    final_results = None

    async with async_playwright() as playwright:
        context = None
        page = None
        try:
            context = await _launch_persistent_context(playwright, user_data_dir)
            await context.add_init_script(ANTI_BOT_INIT_SCRIPT)
            page = await context.new_page()
            _register_itdog_finish_listener(page, test_finished_event)

            logger.info("打开 IT-Dog 页面...")
            try:
                await page.goto(ITDOG_URL, timeout=60000, wait_until="domcontentloaded")
            except Exception as exc:
                logger.warning("首次加载 IT-Dog 异常，尝试刷新: %s", exc)
                await page.reload()

            logger.info("填写 IT-Dog 目标域名: %s", target_host)
            await page.wait_for_timeout(1500)
            await page.get_by_placeholder("例：example.com").fill(target_host)

            logger.info("设置 IT-Dog 自定义 DNS: %s", custom_dns)
            await page.get_by_role("button", name="高级选项").click()
            await page.locator('input[name="dns_server_type"][value="custom"]').check(force=True)
            await page.locator("#dns_server").fill(custom_dns)

            logger.info("开始执行 IT-Dog 快速测试...")
            await page.get_by_role("button", name="快速测试").click()

            logger.info("等待 IT-Dog 结果，最大 60 秒...")
            await asyncio.wait_for(test_finished_event.wait(), timeout=60)
            final_results = await _extract_itdog_results(page)
        except Exception as exc:
            logger.error("IT-Dog 测试执行失败: host=%s error=%s", target_host, exc)
            await _save_debug_screenshot(page, "linux_error.png", "IT-Dog")
        finally:
            if context is not None:
                await context.close()

    return final_results


async def run_cesu_test(target_urls: list[str], cookies: list[dict[str, object]] | None = None):
    """执行 CESU.AI 批量测速。"""
    if not target_urls:
        logger.error("CESU 目标 URL 列表不能为空。")
        return None

    user_data_dir = _get_user_data_dir("cesu_userdata")
    test_finished_event = asyncio.Event()
    final_results = None

    async with async_playwright() as playwright:
        context = None
        page = None
        try:
            context = await _launch_persistent_context(playwright, user_data_dir)
            await context.add_init_script(ANTI_BOT_INIT_SCRIPT)
            if cookies:
                logger.info("检测到传入 Cookies，准备注入 %s 条。", len(cookies))
                await context.add_cookies(cookies)

            page = await context.new_page()
            _register_cesu_finish_listener(page, test_finished_event, len(target_urls))

            logger.info("打开 CESU 批量测速页面...")
            try:
                await page.goto(CESU_URL, timeout=60000, wait_until="domcontentloaded")
            except Exception as exc:
                logger.warning("首次加载 CESU 异常，尝试刷新: %s", exc)
                await page.reload()

            textarea = page.locator('textarea[name="host"]')
            submit_button = page.locator('span.action_submit[data-type="batch"]')

            logger.info("等待 CESU 页面核心元素可用...")
            await textarea.wait_for(state="visible", timeout=30000)
            await submit_button.wait_for(state="visible", timeout=30000)

            logger.info("填写 CESU 批量测试目标: count=%s", len(target_urls))
            await textarea.fill("\n".join(target_urls))

            logger.info("开始执行 CESU 批量测试...")
            await submit_button.click(force=True)

            wait_timeout = 120 * len(target_urls)
            logger.info("等待 CESU 结果，最大 %s 秒...", wait_timeout)
            await asyncio.wait_for(test_finished_event.wait(), timeout=wait_timeout)
            final_results = await _extract_cesu_results(page)
        except Exception as exc:
            logger.error("CESU 测试执行失败: error=%s", exc)
            await _save_debug_screenshot(page, "cesu_error.png", "CESU")
        finally:
            if context is not None:
                logger.info("关闭 CESU 浏览器上下文。")
                await context.close()

    return final_results


if __name__ == "__main__":
    configure_logging(format_string="%(asctime)s - %(levelname)s - [WebTest] - %(message)s")

    json_output = asyncio.run(run_itdog_test(target_host="www.baidu.com", custom_dns="119.29.29.29"))
    if json_output:
        logger.info("IT-Dog 测试完成，结果长度: %s", len(json_output))
    else:
        logger.warning("脚本执行完毕，但未能获取到 IT-Dog JSON 结果。")
