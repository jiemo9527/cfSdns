import asyncio
import json
from playwright.async_api import async_playwright


async def run_itdog_test(target_host: str, custom_dns: str):
    """
    使用Playwright全自动执行IT-Dog网站测速，并返回清洗、格式化后的JSON结果。

    :param target_host: 需要测试的目标域名或IP地址。
    :param custom_dns: 用于测试的自定义DNS服务器IP。
    :return: 包含测试结果的JSON字符串，如果失败则返回None。
    """
    # 创建一个异步事件，用作测试完成的信号
    test_finished_event = asyncio.Event()

    # 最终的JSON结果
    final_results = None

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            print(f"步骤 1: 浏览器启动，正在导航到 https://www.itdog.cn/http/ ...")
            await page.goto("https://www.itdog.cn/http/", timeout=60000, wait_until="networkidle")
            print("页面加载完成。")

            # --- WebSocket 监听器 ---
            def handle_ws_message(ws):
                def process_payload(payload_str):
                    try:
                        data = json.loads(payload_str)
                        if data.get("type") == "finished":
                            print("\n检测到 WebSocket 中的 'type: finished' 信号，测试完成！")
                            test_finished_event.set()
                    except (json.JSONDecodeError, TypeError):
                        pass

                ws.on("framereceived", process_payload)

            page.on("websocket", handle_ws_message)
            print("WebSocket 监听器已设置，将静默运行直到测试结束...")

            # --- 步骤 2: 操作页面 ---
            print(f"步骤 2: 填写测试域名: {target_host}")
            await page.get_by_placeholder("例：example.com 、https://example.com/xxx.html").fill(target_host)

            print("步骤 3: 展开高级选项并设置自定义DNS...")
            await page.get_by_role("button", name="高级选项").click()
            await page.locator('input[name="dns_server_type"][value="custom"]').check()
            await page.locator('#dns_server').fill(custom_dns)
            print(f"成功设置DNS为: {custom_dns}")

            print("步骤 4: 点击“快速测试”按钮...")
            await page.get_by_role("button", name="快速测试").click()
            print("测试已启动，正在等待完成信号...")

            await asyncio.wait_for(test_finished_event.wait(), timeout=300)

            # --- 步骤 5: 在浏览器中解析表格并提取为清洗后的JSON ---
            print("\n步骤 5: 正在提取并清洗结果表格，转换为JSON...")

            # 【核心修正】注入的JavaScript代码现在会进行数据清洗和字段过滤
            results = await page.evaluate('''() => {
                const table = document.querySelector("#simpletable");
                if (!table) return null;

                // 提取表头，并过滤掉我们不需要的列
                const unwanted_headers = ['Head', '赞助商广告'];
                const headers = Array.from(table.querySelectorAll("thead th"))
                                     .map((th, index) => ({ text: th.innerText.trim(), index }))
                                     .filter(header => !unwanted_headers.includes(header.text));

                const rows = Array.from(table.querySelectorAll("tbody tr.node_tr"));

                const data = rows.map(row => {
                    const cells = Array.from(row.querySelectorAll("td"));
                    const rowData = {};

                    headers.forEach(headerInfo => {
                        const cell = cells[headerInfo.index];
                        if (cell) {
                            let cellContent = cell.innerText.trim();
                            // 如果是“检测点”这一列，进行特别清洗
                            if (headerInfo.text === '检测点') {
                                // 将换行符和多个空白符替换为单个空格
                                cellContent = cellContent.replace(/\\s+/g, ' ').trim();
                            }
                            rowData[headerInfo.text] = cellContent;
                        } else {
                            rowData[headerInfo.text] = '';
                        }
                    });
                    return rowData;
                });

                return data;
            }''')

            if results:
                final_results = json.dumps(results, indent=2, ensure_ascii=False)
            else:
                print("错误：未能找到结果表格 #simpletable。")

        except Exception as e:
            await page.screenshot(path="error_screenshot.png")
            print(f"\n操作页面时发生错误: {e}")
            print("已保存截图到 error_screenshot.png 文件，请查看。")
        finally:
            if 'browser' in locals() and browser.is_connected():
                await browser.close()
                print("\n浏览器已关闭。")

    return final_results


async def run_cesu_test(target_urls: list, cookies: list = None):
    """
    使用Playwright全自动执行 CESU.AI 批量网站测速，并返回最终清洗、结构化后的JSON结果。

    :param target_urls: 需要测试的URL列表 (例如: ["https://www.cesu.ai"])
    :param cookies: (可选) 一个包含Cookie字典的列表。如果为None，则不注入Cookie。
    :return: 包含测试结果的JSON字符串，如果失败则返回None。
    """
    if not target_urls:
        print("错误：目标URL列表不能为空。")
        return None

    num_urls = len(target_urls)
    finish_count = 0
    test_finished_event = asyncio.Event()
    final_results = None

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)  # 调试时可改为 headless=False
            context = await browser.new_context()

            if cookies:
                print("检测到传入Cookie，正在设置...")
                await context.add_cookies(cookies)
                print("Cookie 设置成功。")
            else:
                print("未传入Cookie，将以游客状态执行。")

            page = await context.new_page()

            print("--- [CESU.AI] 任务开始 ---")
            print(f"步骤 1: 浏览器启动，共 {num_urls} 个URL待测试...")

            # --- [代码优化] ---
            # 1. 优化页面加载策略，仅等待DOM加载完成，不必等待所有资源
            await page.goto("https://www.cesu.ai/http_batch", timeout=60000, wait_until="domcontentloaded")
            print("页面基本结构加载完成。")

            # 2. 显式等待核心交互元素加载完成，确保脚本稳定
            print("步骤 1a: 等待核心交互元素加载...")
            textarea = page.locator('textarea[name="host"]')
            submit_button = page.locator('span.action_submit[data-type="batch"]')

            await textarea.wait_for(state="visible", timeout=30000)
            await submit_button.wait_for(state="visible", timeout=30000)
            print("核心交互元素加载成功，准备执行操作。")

            # --- [优化结束] ---

            def handle_ws_message(ws):
                nonlocal finish_count

                def process_payload(payload_str):
                    nonlocal finish_count
                    if isinstance(payload_str, str):
                        try:
                            data = json.loads(payload_str)
                            if isinstance(data, dict) and data.get("message") == "finish":
                                finish_count += 1
                                print(f"\n[CESU.AI] 检测到结束信号 ({finish_count}/{num_urls})。")
                                if finish_count >= num_urls:
                                    print("\n[CESU.AI] 所有目标的测试均已完成！")
                                    test_finished_event.set()
                        except (json.JSONDecodeError, TypeError):
                            pass

                ws.on("framereceived", process_payload)

            page.on("websocket", handle_ws_message)
            print("WebSocket 监听器已设置。")

            print("步骤 2: 正在定位并填写测试URL...")
            urls_to_test = "\n".join(target_urls)
            await textarea.fill(urls_to_test)  # 使用之前定位好的元素
            print(f"成功填写 {len(target_urls)} 个URL。")

            print("步骤 3: 点击“批量检测”按钮并等待页面跳转...")
            async with page.expect_navigation(wait_until="networkidle", timeout=60000):
                await submit_button.click()  # 使用之前定位好的元素
            print("页面跳转成功，测试已启动，正在等待所有任务完成信号...")

            await asyncio.wait_for(test_finished_event.wait(), timeout=120 * num_urls)

            print("\n步骤 4: 等待秒，确保前端完全渲染表格...")
            await page.wait_for_timeout(2400)

            print("\n步骤 5: 正在提取、拆分并结构化结果表格为JSON...")
            results = await page.evaluate('''() => {
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
                            const parts = cellText.split('\\n');
                            const timeAndStatus = parts[0].trim();
                            let status = '', time = '', ip = '', ip_location = '';
                            if (isNaN(parseInt(timeAndStatus, 10))) {
                                status = timeAndStatus; time = '--';
                            } else {
                                status = timeAndStatus.substring(0, 3); time = timeAndStatus.substring(3);
                            }
                            if (parts.length > 1) {
                                const ipInfo = parts.slice(1).join(' ').trim();
                                const match = ipInfo.match(/^[\\d\\.:a-fA-F]+\\s*\\[.*\\]$/) 
                                    ? ipInfo.match(/^([\\d\\.:a-fA-F]+)\\s*\\[(.*)\\]$/) 
                                    : [null, ipInfo, ''];
                                if (match) { ip = match[1] || ipInfo; ip_location = match[2] || ''; }
                            }
                            rowData[header] = { "状态": status, "耗时": time, "IP": ip, "IP归属地": ip_location };
                        } else { rowData[header] = cellText; }
                    });
                    return rowData;
                });
            }''')

            if results:
                final_results = json.dumps(results, indent=2, ensure_ascii=False)
            else:
                print("错误：未能找到结果表格 table.table.table_cont。");

        except Exception as e:
            await page.screenshot(path="cesu_ai_error.png")
            print(f"\n[CESU.AI] 操作页面时发生错误: {e}")
            print("已保存截图到 cesu_ai_error.png 文件，请查看。")
        finally:
            if 'browser' in locals() and browser.is_connected():
                await browser.close()
                print("\n[CESU.AI] 浏览器已关闭。")

    return final_results


# ---测试 ---
if __name__ == "__main__":

    ## 测试run_itdog_test
    # json_output = asyncio.run(run_itdog_test(target_host="1.1.1.1", custom_dns="119.29.29.29"))
    # if json_output:
    #     print(json_output)
    # else:
    #     print("\n脚本执行完毕，但未能获取到JSON结果。")
    ## 测试run_cesu_test

    cesuck = [

    ]
    json_output = asyncio.run(run_cesu_test(target_urls=["1.1.1.1"], cookies=cesuck))
    if json_output:
        print(json_output)
    else:
        print("\n[CESU.AI] 未能获取到JSON结果。")