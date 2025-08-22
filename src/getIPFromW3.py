import requests
import re
from typing import List, Tuple
from bs4 import BeautifulSoup
import cloudscraper
from getv3data import v3data



# --- 2. IP提取函数 ---

def extract_ips_from_api(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从API接口获取IP，并根据丢包率筛选。"""
    local_cm, local_cu, local_ct = [], [], []
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"【错误】: 请求API '{url}' 时发生错误: {e}")
        return [], [], []

    ip_data = data.get("data", {})
    all_ips_info = {}
    # 遍历API返回数据，并使用字典对IP进行去重
    for provider_key, ips_list in ip_data.items():
        if isinstance(ips_list, list):
            for ip_info in ips_list:
                if isinstance(ip_info, dict) and 'ip' in ip_info:
                    all_ips_info[ip_info['ip']] = ip_info

    # 根据不同运营商的丢包率将IP分配到对应列表
    for ip, ip_info in all_ips_info.items():
        if ip_info.get("ydPkgLostRateAvg", 100) < 3.5:  # 移动
            local_cm.append(ip)
        if ip_info.get("ltPkgLostRateAvg", 100) < 0.5:  # 联通
            local_cu.append(ip)
        if ip_info.get("dxPkgLostRateAvg", 100) < 3.5:  # 电信
            local_ct.append(ip)

    return local_cm, local_cu, local_ct


def extract_table_ips_from_html(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从HTML页面的表格中提取IP，并按运营商分类。"""
    cm_ips, cu_ips, ct_ips = [], [], []
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return [], [], []

        # 遍历表格行，提取运营商名称和IP地址
        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > 1:
                name = cols[0].text.strip()
                ip = cols[1].text.strip()
                # 验证IP格式
                if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    # <<< 修改：只处理电信、联通、移动 >>>
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
    """从纯文本页面提取以逗号分隔的IP地址。"""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        ip_text = response.text.strip()
        # 切分文本并验证每个IP的格式
        ip_list = [ip.strip() for ip in ip_text.split(',') if
                   re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip.strip())]
        return ip_list, ip_list, ip_list
    except Exception as e:
        print(f"【错误】: 从URL '{url}' 提取文本IP失败: {e}")
        return [], [], []


# --- 3. 主处理函数 ---
def get_cf_ips() -> Tuple[List[str], List[str], List[str]]:
    """执行获取、合并和处理Cloudflare IP的完整流程。"""
    all_cm_ips, all_cu_ips, all_ct_ips = [], [], []

    # 步骤 2: 从v3data获取IP
    try:
        cm_ip_v3, cu_ip_v3, ct_ip_v3 = v3data()
        all_cm_ips.extend(cm_ip_v3)
        all_cu_ips.extend(cu_ip_v3)
        all_ct_ips.extend(ct_ip_v3)
        print(f"v3data 获取完成。移动 {len(cm_ip_v3)}, 联通 {len(cu_ip_v3)}, 电信 {len(ct_ip_v3)} 个IP。")
    except Exception as e:
        print(f"【错误】: 执行 v3data() 时发生意外: {e}。")

    # 步骤 3: 从其他来源获取IP
    # 从 api.uouin.com
    cm_u, cu_u, ct_u = extract_table_ips_from_html("https://api.uouin.com/cloudflare.html")
    all_cm_ips.extend(cm_u)
    all_cu_ips.extend(cu_u)
    all_ct_ips.extend(ct_u)
    print(f"api.uouin.com 获取完成。移动 {len(cm_u)}, 联通 {len(cu_u)}, 电信 {len(ct_u)} 个IP。")

    # 从 wetest.vip
    cm_w, cu_w, ct_w = extract_table_ips_from_html("https://www.wetest.vip/page/cloudflare/address_v4.html")
    all_cm_ips.extend(cm_w)
    all_cu_ips.extend(cu_w)
    all_ct_ips.extend(ct_w)
    print(f"wetest.vip 获取完成。移动 {len(cm_w)}, 联通 {len(cu_w)}, 电信 {len(ct_w)} 个IP。")

    # 从 cf.090227.xyz (每种最多取10个)
    cm_cf, cu_cf, ct_cf = extract_table_ips_from_html("https://cf.090227.xyz")
    all_cm_ips.extend(cm_cf[:10])
    all_cu_ips.extend(cu_cf[:10])
    all_ct_ips.extend(ct_cf[:10])
    print(f"cf.090227.xyz 获取完成。移动 {len(cm_cf)}, 联通 {len(cu_cf)}, 电信 {len(ct_cf)} 个IP")

    # 从 ip.164746.xyz
    cm_16, cu_16, ct_16 = extract_ips_from_text("https://ip.164746.xyz/ipTop10.html")
    all_cm_ips.extend(cm_16)
    all_cu_ips.extend(cu_16)
    all_ct_ips.extend(ct_16)
    print(f"ip.164746.xyz 获取完成。共 {len(cm_16)} 个IP。")

    # 步骤 4: 列表去重和排序
    print("\n--- 开始处理和合并IP列表 ---")
    final_ct_ip = sorted(list(set(all_ct_ips)))
    final_cm_ip = sorted(list(set(all_cm_ips)))
    final_cu_ip = sorted(list(set(all_cu_ips)))

    # 步骤 5: 剔除指定网段的IP
    print("\n---  剔除 172.65.*.* 网段的IP ---")
    final_ct_ip_filtered = [ip for ip in final_ct_ip if not ip.startswith("172.65.")]
    final_cm_ip_filtered = [ip for ip in final_cm_ip if not ip.startswith("172.65.")]
    final_cu_ip_filtered = [ip for ip in final_cu_ip if not ip.startswith("172.65.")]

    # 步骤 6: 限制每个列表的IP数量
    final_ct_ip_limited = final_ct_ip_filtered[-50:]
    final_cm_ip_limited = final_cm_ip_filtered[-50:]
    final_cu_ip_limited = final_cu_ip_filtered[-50:]

    print(
        f"处理后：电信 {len(final_ct_ip_limited)} 个, 移动 {len(final_cm_ip_limited)} 个, 联通 {len(final_cu_ip_limited)} 个。")
    print("\n--- IP获取任务执行完毕 ---")
    return final_ct_ip_limited, final_cm_ip_limited, final_cu_ip_limited


# --- 4. 主程序入口 ---
if __name__ == '__main__':
    # 执行主函数并获取处理后的IP列表
    ct_ip, cm_ip, cu_ip = get_cf_ips()
    # 打印最终结果
    print("\n--- 最终获取到的IP列表 (已剔除 172.65.*.*) ---")
    print(f"电信IP ({len(ct_ip)}个): {ct_ip}")
    print(f"移动IP ({len(cm_ip)}个): {cm_ip}")
    print(f"联通IP ({len(cu_ip)}个): {cu_ip}")