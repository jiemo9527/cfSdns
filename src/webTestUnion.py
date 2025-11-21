import asyncio
import json
import os
import platform
from playwright.async_api import async_playwright


async def run_itdog_test(target_host: str, custom_dns: str):
    """
    Windows/Linux 通用兼容版。
    自动处理路径，配合 XVFB 在 Linux 上实现伪装。
    """
    # 1. 动态设置 User Data 路径 (使用相对路径，跨平台兼容)
    # 在脚本同级目录下生成 ./itdog_userdata 文件夹
    current_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(current_dir, "itdog_userdata")

    # 2. 检测操作系统
    system_name = platform.system()
    print(f"当前运行环境: {system_name}")
    print(f"用户数据目录: {user_data_dir}")

    # 3. 关键伪装参数 (Linux下存活的关键)
    # 即使是新生成的 Profile，加上这些参数也能极大幅度降低被杀概率
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-size=1920,1080",  # 强制设置分辨率
    ]

    ignore_args = ["--enable-automation"]

    test_finished_event = asyncio.Event()
    final_results = None

    async with async_playwright() as p:
        try:
            # 4. 启动浏览器
            # 注意：在 Linux 上我们依然设置 headless=False，依靠 xvfb 来运行
            # 这样可以保留浏览器的完整指纹
            print("正在启动浏览器 (持久化模式)...")

            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,  # 重点！无论 Win 还是 Linux 都设为 False
                args=launch_args,
                ignore_default_args=ignore_args,
                viewport={"width": 1920, "height": 1080},
                # Linux 上可能没有安装 Google Chrome，所以去掉 channel="chrome"，使用默认 Chromium 兼容性更好
                # 如果你 Windows 上报错，可以把下面这行取消注释：
                # channel="chrome" if system_name == "Windows" else None
            )

            page = await context.new_page()

            # 5. 注入防检测 JS (双重保险)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            print(f"步骤 1: 导航到 ITDOG...")
            try:
                await page.goto("https://www.itdog.cn/http/", timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"首次加载异常 (可能是网络波动): {e}，尝试刷新...")
                await page.reload()

            # --- WebSocket 监听器 ---
            def handle_ws_message(ws):
                def process_payload(payload_str):
                    try:
                        data = json.loads(payload_str)
                        if data.get("type") == "finished":
                            print(">>> 检测到完成信号！")
                            test_finished_event.set()
                    except:
                        pass

                ws.on("framereceived", process_payload)

            page.on("websocket", handle_ws_message)

            # --- 页面操作 ---
            print(f"步骤 2: 填写目标 {target_host}")
            # 稍微 sleep 一下，模拟真人
            await page.wait_for_timeout(1500)
            await page.get_by_placeholder("例：example.com").fill(target_host)

            print("步骤 3: 设置 DNS...")
            await page.get_by_role("button", name="高级选项").click()
            # 使用 force=True 防止被悬浮窗遮挡
            await page.locator('input[name="dns_server_type"][value="custom"]').check(force=True)
            await page.locator('#dns_server').fill(custom_dns)

            print("步骤 4: 点击测试...")
            await page.get_by_role("button", name="快速测试").click()

            print("等待结果 (最多60秒)...")
            await asyncio.wait_for(test_finished_event.wait(), timeout=60)

            # --- 结果提取 ---
            print("步骤 5: 提取数据...")
            # 给一点时间让表格最后渲染
            await page.wait_for_timeout(1000)

            results = await page.evaluate('''() => {
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
                        rowData[h.text] = cells[h.index] ? cells[h.index].innerText.trim().replace(/\\s+/g, ' ') : '';
                    });
                    return rowData;
                });
            }''')

            if results:
                final_results = json.dumps(results, indent=2, ensure_ascii=False)
            else:
                print("警告：未找到结果表格。")

        except Exception as e:
            print(f"运行出错: {e}")
            # 保存截图以便在 Linux 上排查
            if 'page' in locals():
                await page.screenshot(path="linux_error.png")
        finally:
            if 'context' in locals():
                await context.close()

    return final_results


async def run_cesu_test(target_urls: list, cookies: list = None):
    """
    [升级版] 全自动执行 CESU.AI 测速。
    特性：
    1. 支持 Windows/Linux 通用路径 (itdog/cesu 分离存储)。
    2. 使用 headless=False + 伪装参数绕过反爬。
    3. 必须配合 xvfb 在 Linux 上运行。
    """
    if not target_urls:
        print("错误：目标URL列表不能为空。")
        return None

    # --- 1. 路径与系统配置 (复用核心策略) ---
    # 在脚本同级目录下生成独立的 ./cesu_userdata 文件夹，避免跟 itdog 冲突
    current_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(current_dir, "cesu_userdata")

    print(f"[CESU] 用户数据目录: {user_data_dir}")

    # 核心伪装参数
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-size=1920,1080",
    ]
    ignore_args = ["--enable-automation"]

    num_urls = len(target_urls)
    finish_count = 0
    test_finished_event = asyncio.Event()
    final_results = None

    async with async_playwright() as p:
        try:
            # --- 2. 启动浏览器 (持久化模式) ---
            print(f"步骤 1: 启动浏览器 (Headless=False 伪装模式)...")

            # 使用 launch_persistent_context 替代 launch
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,  # 关键：Linux下配合xvfb使用
                args=launch_args,
                ignore_default_args=ignore_args,
                viewport={"width": 1920, "height": 1080}
            )

            # --- 3. 注入防检测脚本 ---
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            # 如果传入了特定的 cookies 参数，手动注入
            # (注意：持久化模式会自动保存之前的 cookie，这里仅用于强制覆盖或首次注入)
            if cookies:
                print("检测到传入 Cookies，正在注入...")
                await context.add_cookies(cookies)

            page = await context.new_page()

            print(f"步骤 1a: 导航到 CESU 批量页面...")
            try:
                await page.goto("https://www.cesu.ai/http_batch", timeout=60000, wait_until="domcontentloaded")
            except Exception:
                print("首次加载超时，尝试刷新...")
                await page.reload()

            print("步骤 1b: 等待核心元素...")
            textarea = page.locator('textarea[name="host"]')
            submit_button = page.locator('span.action_submit[data-type="batch"]')

            await textarea.wait_for(state="visible", timeout=30000)
            await submit_button.wait_for(state="visible", timeout=30000)

            # --- WebSocket 监听器 ---
            def handle_ws_message(ws):
                nonlocal finish_count

                def process_payload(payload_str):
                    nonlocal finish_count
                    if isinstance(payload_str, str):
                        try:
                            data = json.loads(payload_str)
                            if isinstance(data, dict) and data.get("message") == "finish":
                                finish_count += 1
                                print(f"\r[CESU] 进度: {finish_count}/{num_urls}", end="", flush=True)
                                if finish_count >= num_urls:
                                    print("\n[CESU] 所有任务完成！")
                                    test_finished_event.set()
                        except (json.JSONDecodeError, TypeError):
                            pass

                ws.on("framereceived", process_payload)

            page.on("websocket", handle_ws_message)

            # --- 页面交互 ---
            print("\n步骤 2: 填写 URL...")
            urls_to_test = "\n".join(target_urls)
            await textarea.fill(urls_to_test)

            print("步骤 3: 点击测试...")
            # 防止点击被浮层遮挡
            await submit_button.click(force=True)

            # 动态等待时间：每个URL给足时间，防止过早超时
            wait_timeout = 120 * num_urls
            print(f"等待测试完成 (最大超时 {wait_timeout}秒)...")

            await asyncio.wait_for(test_finished_event.wait(), timeout=wait_timeout)

            print("\n步骤 4: 等待表格渲染缓冲 (2.5秒)...")
            await page.wait_for_timeout(2500)

            # --- 数据提取 ---
            print("步骤 5: 提取清洗数据...")
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
                print("错误：未能找到结果表格 table.table.table_cont。")

        except Exception as e:
            print(f"\n[CESU] 发生错误: {e}")
            if 'page' in locals():
                await page.screenshot(path="cesu_error.png")
                print("已保存错误截图 cesu_error.png")
        finally:
            # 持久化模式必须关闭 context
            if 'context' in locals():
                print("[CESU] 关闭浏览器上下文...")
                await context.close()

    return final_results


# ---测试 ---
if __name__ == "__main__":

    ## 测试run_itdog_test
    json_output = asyncio.run(run_itdog_test(target_host="www.baidu.com", custom_dns="119.29.29.29"))
    if json_output:
        print(json_output)
    else:
        print("\n脚本执行完毕，但未能获取到JSON结果。")

    ## 测试run_cesu_test
    # cesuck = [
    #
    # ]
    # json_output = asyncio.run(run_cesu_test(target_urls=["1.1.1.1"], cookies=cesuck))
    # if json_output:
    #     print(json_output)
    # else:
    #     print("\n[CESU.AI] 未能获取到JSON结果。")