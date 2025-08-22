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


# ---测试 ---
if __name__ == "__main__":
    # 定义要测试的目标和使用的DNS
    test_target = "1.1.1.1"
    dns_server = "119.29.29.29"

    # 运行测试函数
    json_output = asyncio.run(run_itdog_test(target_host=test_target, custom_dns=dns_server))
    # 打印最终结果
    if json_output:
        print(json_output)
    else:
        print("\n脚本执行完毕，但未能获取到JSON结果。")