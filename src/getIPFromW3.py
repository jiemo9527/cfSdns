import requests
import json
import re
from typing import List, Tuple
from bs4 import BeautifulSoup
import cloudscraper
from getv3data import v3data

#每日api
def extract_ips_from_api(url: str) -> Tuple[List[str], List[str], List[str]]:
    """
    从指定的URL获取IP。此函数内部包含了网络请求、JSON解析和数据处理的异常捕获。
    """
    local_cm, local_cu, local_ct = [], [], []
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"【错误】: 请求API '{url}' 时发生错误: {e}")
        return [], [], []
    except json.JSONDecodeError:
        print(f"【错误】: 解析来自 '{url}' 的响应失败，内容不是有效的JSON格式。")
        return [], [], []

    ip_data = data.get("data")
    if not isinstance(ip_data, dict):
        print(f"【警告】: API响应中 'data' 字段的格式不正确（不是字典），无法提取IP。")
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

        if yd_loss < 3.5:
            local_cm.append(ip)
        if lt_loss < 0.5:
            local_cu.append(ip)
        if dx_loss < 3.5:
            local_ct.append(ip)

    return local_cm, local_cu, local_ct

#其他1
def extract_table_ips_from_html(url: str) -> Tuple[List[str], List[str], List[str]]:
    """
    从指定的URL的HTML页面中提取IP。
    """
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

#其他2
def extract_ips_from_text(url: str) -> Tuple[List[str], List[str], List[str]]:
    """
    从指定的URL中提取文本形式的IP地址。
    """
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


# --- 处理函数 ---
def get_cf_ips() -> Tuple[List[str], List[str], List[str]]:
    """
    执行获取、合并和处理Cloudflare IP的完整流程。
    返回:
        tuple: 包含三个处理后列表的元组 (ct_ip, cm_ip, cu_ip)
    """
    print("--- 开始执行IP获取任务 ---")
    all_cm_ips, all_cu_ips, all_ct_ips = [], [], []

    # 步骤 1: 从API获取IP
    print("步骤 1: 正在从 API 获取IP...")
    cm_ip_api, cu_ip_api, ct_ip_api = extract_ips_from_api("https://vps789.com/openApi/cfIpApi")
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

    # 从 wetest.vip
    cm_w, cu_w, ct_w = extract_table_ips_from_html("https://www.wetest.vip/page/cloudflare/address_v4.html")
    all_cm_ips.extend(cm_w)
    all_cu_ips.extend(cu_w)
    all_ct_ips.extend(ct_w)

    # 从 cf.090227.xyz
    cm_cf, cu_cf, ct_cf = extract_table_ips_from_html("https://cf.090227.xyz")
    # 限制每种类型最多10个
    all_cm_ips.extend(cm_cf[:10])
    all_cu_ips.extend(cu_cf[:10])
    all_ct_ips.extend(ct_cf[:10])

    # 从 ip.164746.xyz
    cm_16, cu_16, ct_16 = extract_ips_from_text("https://ip.164746.xyz/ipTop10.html")
    all_cm_ips.extend(cm_16)
    all_cu_ips.extend(cu_16)
    all_ct_ips.extend(ct_16)

    # 步骤 4: 处理每个列表 (去重、排序)
    print("\n--- 步骤 4: 开始处理和合并IP列表 ---")
    final_ct_ip = sorted(list(set(all_ct_ips)))
    final_cm_ip = sorted(list(set(all_cm_ips)))
    final_cu_ip = sorted(list(set(all_cu_ips)))

    # 步骤 5: 剔除指定网段的IP
    print("\n--- 步骤 5: 剔除 172.65.*.* 网段的IP ---")
    final_ct_ip_filtered = [ip for ip in final_ct_ip if not ip.startswith("172.65.")]
    final_cm_ip_filtered = [ip for ip in final_cm_ip if not ip.startswith("172.65.")]
    final_cu_ip_filtered = [ip for ip in final_cu_ip if not ip.startswith("172.65.")]

    # 步骤 6: 限制每个列表最多50个 (在剔除之后)
    final_ct_ip_limited = final_ct_ip_filtered[-50:]
    final_cm_ip_limited = final_cm_ip_filtered[-50:]
    final_cu_ip_limited = final_cu_ip_filtered[-50:]

    print(
        f"处理后：电信 {len(final_ct_ip_limited)} 个, 移动 {len(final_cm_ip_limited)} 个, 联通 {len(final_cu_ip_limited)} 个。")
    print(f"电信IP: 剔除 {len(final_ct_ip) - len(final_ct_ip_filtered)} 个, 最终 {len(final_ct_ip_limited)} 个。")
    print(f"移动IP: 剔除 {len(final_cm_ip) - len(final_cm_ip_filtered)} 个, 最终 {len(final_cm_ip_limited)} 个。")
    print(f"联通IP: 剔除 {len(final_cu_ip) - len(final_cu_ip_filtered)} 个, 最终 {len(final_cu_ip_limited)} 个。")

    print("\n--- IP获取任务执行完毕 ---")
    return final_ct_ip_limited, final_cm_ip_limited, final_cu_ip_limited


# --- 4. 主程序入口与示例调用 ---
if __name__ == '__main__':
    ct_ip, cm_ip, cu_ip = get_cf_ips()
    print("\n--- 最终获取到的IP列表 (已剔除 172.65.*.*) ---")
    print(f"电信IP ({len(ct_ip)}个): {ct_ip}")
    print(f"移动IP ({len(cm_ip)}个): {cm_ip}")
    print(f"联通IP ({len(cu_ip)}个): {cu_ip}")