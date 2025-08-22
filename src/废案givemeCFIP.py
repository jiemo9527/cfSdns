import requests
import json
import re
import asyncio
import aiohttp
from typing import List, Tuple
from bs4 import BeautifulSoup
import cloudscraper
from getv3data import v3data

# --- 1. 模块导入与设置 ---
# 全局常量
API_URL = "https://vps789.com/openApi/cfIpApi"
PING_API_URL = "https://v2.xxapi.cn/api/ping?url="  # ping API 地址
DOMAIN_LIST = [
    "store.epicgames.com", "cdnjs.com", "www.racknerd.com", "www.epicgames.com",
    "www.visa.com.tw", "qa.visamiddleeast.com", "cloudflare-ip.mofashi.ltd",
    "fbi.gov", "www.to.org", "www.fortnite.com", "ns3.cloudflare.com",
    "ns6.cloudflare.com", "ns4.cloudflare.com", "ns5.cloudflare.com",
    "radar.cloudflare.com",
]


# --- 2. 辅助函数定义 ---
def extract_ips_from_api(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从指定的URL获取IP。"""
    local_cm, local_cu, local_ct = [], [], []
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"【错误】: 请求API '{url}' 时发生错误: {e}")
        return [], [], []
    except json.JSONDecodeError:
        print(f"【错误】: 解析来自 '{url}' 的响应失败。")
        return [], [], []

    ip_data = data.get("data")
    if not isinstance(ip_data, dict):
        print(f"【警告】: API响应中 'data' 字段的格式不正确。")
        return [], [], []

    all_ips_info = {}
    for provider_key, ips_list in ip_data.items():
        if not isinstance(ips_list, list):
            continue
        for ip_info in ips_list:
            if isinstance(ip_info, dict) and 'ip' in ip_info:
                all_ips_info[ip_info['ip']] = ip_info

    for ip, ip_info in all_ips_info.items():
        yd_loss = ip_info.get("ydPkgLostRateAvg", float('inf'))
        lt_loss = ip_info.get("ltPkgLostRateAvg", float('inf'))
        dx_loss = ip_info.get("dxPkgLostRateAvg", float('inf'))

        if yd_loss < 3.3:
            local_cm.append(ip)
        if lt_loss < 0.5:
            local_cu.append(ip)
        if dx_loss < 3.3:
            local_ct.append(ip)

    return local_cm, local_cu, local_ct


def extract_table_ips_from_html(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从指定的URL的HTML页面中提取IP。"""
    cm_ips, cu_ips, ct_ips = [], [], []
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if not table:
            print(f"【警告】: 在URL '{url}' 中未找到表格。")
            return [], [], []

        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > 1:
                name = cols[0].text.strip()
                ip = cols[1].text.strip()
                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    continue

                if "移动" in name:
                    cm_ips.append(ip)
                elif "联通" in name:
                    cu_ips.append(ip)
                elif "电信" in name:
                    ct_ips.append(ip)
    except Exception as e:
        print(f"【错误】: 从URL '{url}' 提取表格数据失败: {e}")
        return [], [], []

    return cm_ips, cu_ips, ct_ips


def extract_ips_from_text(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从指定的URL中提取文本形式的IP地址。"""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        ip_text = response.text.strip()
        ip_list = [ip.strip() for ip in ip_text.split(',') if
                   re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip.strip())]

        return ip_list, ip_list, ip_list
    except Exception as e:
        print(f"【错误】: 从URL '{url}' 提取文本IP失败: {e}")
        return [], [], []


# --- 3. 核心功能函数 ---
def get_cf_ips() -> Tuple[List[str], List[str], List[str]]:
    """
    执行获取、合并、处理和测试Cloudflare IP的完整流程。
    """
    print("--- 开始执行IP获取任务 ---")
    all_cm_ips, all_cu_ips, all_ct_ips = [], [], []

    # 步骤 1: 从API获取IP
    print("步骤 1: 正在从 API 获取IP...")
    cm_ip_api, cu_ip_api, ct_ip_api = extract_ips_from_api(API_URL)
    all_cm_ips.extend(cm_ip_api)
    all_cu_ips.extend(cu_ip_api)
    all_ct_ips.extend(ct_ip_api)
    print(f"API 获取完成。移动 {len(cm_ip_api)}, 联通 {len(cu_ip_api)}, 电信 {len(ct_ip_api)} 个IP。")

    # 步骤 2: 从v3data获取IP
    print("\n步骤 2: 正在从 v3data 获取IP...")
    try:
        cm_ip_v3, cu_ip_v3, ct_ip_v3 = v3data()
        all_cm_ips.extend(cm_ip_v3)
        all_cu_ips.extend(cu_ip_v3)
        all_ct_ips.extend(ct_ip_v3)
        print(f"v3data 获取完成。移动 {len(cm_ip_v3)}, 联通 {len(cu_ip_v3)}, 电信 {len(ct_ip_v3)} 个IP。")
    except Exception as e:
        print(f"【错误】: 执行 v3data() 函数时发生意外: {e}。将跳过此数据源。")

    # 步骤 3: 从其他来源获取IP并合并
    print("\n步骤 3: 正在从其他来源获取IP...")
    cm_w, cu_w, ct_w = extract_table_ips_from_html("https://www.wetest.vip/page/cloudflare/address_v4.html")
    all_cm_ips.extend(cm_w)
    all_cu_ips.extend(cu_w)
    all_ct_ips.extend(ct_w)

    cm_cf, cu_cf, ct_cf = extract_table_ips_from_html("https://cf.090227.xyz")
    all_cm_ips.extend(cm_cf[:10])
    all_cu_ips.extend(cu_cf[:10])
    all_ct_ips.extend(ct_cf[:10])

    cm_16, cu_16, ct_16 = extract_ips_from_text("https://ip.164746.xyz/ipTop10.html")
    all_cm_ips.extend(cm_16)
    all_cu_ips.extend(cu_16)
    all_ct_ips.extend(ct_16)

    # 步骤 4: 处理每个列表 (去重、排序、限制)
    print("\n--- 步骤 4: 开始处理和合并IP列表 ---")
    final_ct_ip = sorted(list(set(all_ct_ips)))[-50:]
    final_cm_ip = sorted(list(set(all_cm_ips)))[-50:]
    final_cu_ip = sorted(list(set(all_cu_ips)))[-50:]
    print(f"处理后：电信 {len(final_ct_ip)} 个, 移动 {len(final_cm_ip)} 个, 联通 {len(final_cu_ip)} 个。")
    print("\n--- IP获取任务执行完毕 ---")

    # 步骤 5: 对IP列表进行Ping测试和最终筛选
    print("\n--- 开始对IP列表进行 Ping 测试 ---")
    print("\n电信IP测试中...")
    ct_reachable_ips = asyncio.run(get_reachable_ips_async(final_ct_ip))
    print("\n移动IP测试中...")
    cm_reachable_ips = asyncio.run(get_reachable_ips_async(final_cm_ip))
    print("\n联通IP测试中...")
    cu_reachable_ips = asyncio.run(get_reachable_ips_async(final_cu_ip))

    print("\n\n--- 最终筛选结果 ---")
    print(f"最终符合要求的电信IP ({len(ct_reachable_ips)}个): {ct_reachable_ips}")
    print(f"最终符合要求的移动IP ({len(cm_reachable_ips)}个): {cm_reachable_ips}")
    print(f"最终符合要求的联通IP ({len(cu_reachable_ips)}个): {cu_reachable_ips}")

    return ct_reachable_ips, cm_reachable_ips, cu_reachable_ips


async def _fetch_ping_once(session: aiohttp.ClientSession, ip: str) -> Tuple[str, dict]:
    """异步地从 API 获取单个 IP 的 ping 结果（单次尝试）。"""
    try:
        async with session.get(f"{PING_API_URL}{ip}", timeout=10) as response:
            data = await response.json()
            return ip, data
    except Exception as e:
        return ip, {"code": -1, "msg": f"API call failed: {e}"}


async def _fetch_ping_with_retry(session: aiohttp.ClientSession, ip: str, max_retries: int = 3) -> Tuple[str, dict]:
    """异步获取ping结果，并在结果小于70ms或API出错时自动重试。"""
    last_data = {}
    for attempt in range(max_retries):
        _ip, data = await _fetch_ping_once(session, ip)
        last_data = data  # 始终保存最后一次的尝试结果

        if data.get("code") == 200 and "data" in data and data["data"]:
            ping_data = data["data"]
            time_str = ping_data.get("time", "超时")
            match = re.search(r"(\d+\.?\d*)ms", time_str)
            if match:
                delay = float(match.group(1))
                if delay >= 70:
                    return ip, data  # 延迟有效(>=70ms)，是有效结果，直接返回

        if attempt < max_retries - 1:
            await asyncio.sleep(0.5)  # 如果不是最后一次尝试，则等待后重试

    return ip, last_data  # 所有重试都失败，返回最后一次的结果


async def get_reachable_ips_async(ips_to_ping: List[str]) -> List[str]:
    """
    使用 API 异步 ping IP 列表，并返回符合条件的 IP。
    - 增加频率控制，避免触发API限制。
    - 如果 ping 结果 < 70ms，则视为错误并重试。
    - 最终筛选条件：70ms <= 延迟 < 300ms。
    """
    if not ips_to_ping:
        return []

    results: List[Tuple[str, dict]] = []

    # 将并发数降低到15，以减少瞬时请求压力
    sem = asyncio.Semaphore(15)

    async def get_with_sem(session, ip):
        async with sem:
            # 确保请求频率远低于API限制 (例如 12次/秒)
            # 1秒 / 12次 ≈ 0.083秒间隔
            await asyncio.sleep(0.083)
            return await _fetch_ping_with_retry(session, ip)

    async with aiohttp.ClientSession() as session:
        tasks = [get_with_sem(session, ip) for ip in ips_to_ping]
        results = await asyncio.gather(*tasks)

    passed_ips: List[str] = []
    for ip, data in results:
        if data.get("code") == 200 and "data" in data and data["data"]:
            time_str = data["data"].get("time", "超时")
            print(f"IP: {ip:<15} | Ping: {time_str:<10}", end="")
            match = re.search(r"(\d+\.?\d*)ms", time_str)
            if match:
                delay = float(match.group(1))
                if delay < 70:
                    print(f" -> [失败 - 结果异常 (延迟 < 70ms)]")
                elif delay < 300:
                    passed_ips.append(ip)
                    print(" -> [通过]")
                else:
                    print(f" -> [失败 - 延迟过高 {delay}ms >= 300ms]")
            else:
                print(" -> [失败 - 无法解析延迟或超时]")
        else:
            error_msg = data.get("msg", "未知API错误")
            print(f"IP: {ip:<15} | Ping: [测试失败] -> [原因: {error_msg}]")

    return passed_ips


# --- 4. 主程序入口（用于独立测试）---
if __name__ == '__main__':
    print("--- 正在以独立测试模式运行 givemeCFIP.py ---")
    # 现在这个代码块仅用于独立测试此脚本。
    # 完整业务逻辑由 main.py 编排执行。
    get_cf_ips()