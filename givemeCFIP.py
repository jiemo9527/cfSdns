import requests
import json  # 用于处理可能的JSON解析错误

# --- 1. 模块导入与设置 (保持在全局作用域) ---
# 尝试导入v3data，如果失败，则定义一个返回空列表的备用函数
try:
    from getv3data import v3data

    print("模块 'getv3data' 导入成功。")
except (ImportError, ModuleNotFoundError):
    print("【警告】: 'getv3data' 模块未找到或导入失败。将跳过此数据源。")


    # 定义一个空的备用(dummy)函数
    def v3data():
        """这是一个备用函数，在主模块导入失败时使用，确保程序不崩溃。"""
        return [], [], []

# 全局常量
API_URL = "https://vps789.com/openApi/cfIpApi"
DOMAIN_LIST = [
    "store.epicgames.com", "cdnjs.com", "www.racknerd.com", "www.epicgames.com",
    "www.visa.com.tw", "qa.visamiddleeast.com", "cloudflare-ip.mofashi.ltd",
    "fbi.gov", "www.wto.org", "www.fortnite.com", "ns3.cloudflare.com",
    "ns6.cloudflare.com", "ns4.cloudflare.com", "ns5.cloudflare.com",
    "radar.cloudflare.com",
]


# --- 2. 辅助函数定义 (保持在全局作用域) ---
def extract_ips_from_api(url):
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

        if yd_loss < 3.3:
            local_cm.append(ip)
        if lt_loss < 0.5:
            local_cu.append(ip)
        if dx_loss < 3.3:
            local_ct.append(ip)

    return local_cm, local_cu, local_ct


# --- 3. 核心功能函数 ---
def get_cf_ips():
    """
    执行获取、合并和处理Cloudflare IP的完整流程。

    返回:
        tuple: 包含三个处理后列表的元组 (ct_ip, cm_ip, cu_ip)
    """
    print("--- 开始执行IP获取任务 ---")

    # 步骤 1: 从API获取IP
    print("步骤 1: 正在从 API 获取IP...")
    cm_ip_api, cu_ip_api, ct_ip_api = extract_ips_from_api(API_URL)
    print(f"API 获取完成。移动 {len(cm_ip_api)}, 联通 {len(cu_ip_api)}, 电信 {len(ct_ip_api)} 个IP")

    # 步骤 2: 从v3data获取IP
    print("\n步骤 2: 正在从 v3data 获取IP...")
    try:
        cm_ip_v3, cu_ip_v3, ct_ip_v3 = v3data()
        print(f"v3data 获取完成。移动 {len(cm_ip_v3)}, 联通 {len(cu_ip_v3)}, 电信 {len(ct_ip_v3)} 个IP")
    except Exception as e:
        print(f"【错误】: 执行 v3data() 函数时发生意外: {e}。将跳过此数据源。")
        cm_ip_v3, cu_ip_v3, ct_ip_v3 = [], [], []

    # 步骤 3: 合并结果
    cm_ip_merged = cm_ip_api + cm_ip_v3
    cu_ip_merged = cu_ip_api + cu_ip_v3
    ct_ip_merged = ct_ip_api + ct_ip_v3

    # 步骤 4: 处理每个列表 (去重、排序、筛选)
    print("\n--- 开始处理IP列表 ---")

    # --- 处理移动IP ---
    unique_cm_ips = sorted(list(set(cm_ip_merged)))
    if len(unique_cm_ips) > 50:
        print(f"移动IP列表去重后共 {len(unique_cm_ips)} 个，超过50个，仅保留最后50个。")
        final_cm_ip = unique_cm_ips[-50:]
    else:
        final_cm_ip = unique_cm_ips
        print(f"移动IP列表去重后共 {len(final_cm_ip)} 个。")

    # --- 处理联通IP ---
    unique_cu_ips = sorted(list(set(cu_ip_merged)))
    if len(unique_cu_ips) > 50:
        print(f"联通IP列表去重后共 {len(unique_cu_ips)} 个，超过50个，仅保留最后50个。")
        final_cu_ip = unique_cu_ips[-50:]
    else:
        final_cu_ip = unique_cu_ips
        print(f"联通IP列表去重后共 {len(final_cu_ip)} 个。")

    # --- 处理电信IP ---
    unique_ct_ips = sorted(list(set(ct_ip_merged)))
    if len(unique_ct_ips) > 50:
        print(f"电信IP列表去重后共 {len(unique_ct_ips)} 个，超过50个，仅保留最后50个。")
        final_ct_ip = unique_ct_ips[-50:]
    else:
        final_ct_ip = unique_ct_ips
        print(f"电信IP列表去重后共 {len(final_ct_ip)} 个。")

    print("\n--- IP获取任务执行完毕 ---")

    # 按照您的要求返回 (电信, 移动, 联通)
    return final_ct_ip, final_cm_ip, final_cu_ip


# --- 4. 主程序入口与示例调用 ---
if __name__ == '__main__':
    # 调用主函数获取IP列表
    ct_ip, cm_ip, cu_ip = get_cf_ips()
