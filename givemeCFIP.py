import requests
import json  # 用于处理可能的JSON解析错误

# --- 1. 对导入模块进行异常处理 ---
# 尝试导入v3data，如果失败，则定义一个返回空列表的备用函数
# 这样无论模块是否存在，程序主体都可以正常运行而不会崩溃
try:
    from getv3data import v3data

    print("模块 'getv3data' 导入成功。")
except (ImportError, ModuleNotFoundError):
    print("【警告】: 'getv3data' 模块未找到或导入失败。将跳过此数据源。")


    # 定义一个空的备用(dummy)函数
    def v3data():
        """这是一个备用函数，在主模块导入失败时使用，确保程序不崩溃。"""
        return [], [], []

# 全局变量和常量
API_URL = "https://vps789.com/openApi/cfIpApi"
domain_list = [
    "store.epicgames.com", "cdnjs.com", "www.racknerd.com", "www.epicgames.com",
    "www.visa.com.tw", "qa.visamiddleeast.com", "cloudflare-ip.mofashi.ltd",
    "fbi.gov", "www.wto.org", "www.fortnite.com", "ns3.cloudflare.com",
    "ns6.cloudflare.com", "ns4.cloudflare.com", "ns5.cloudflare.com",
    "radar.cloudflare.com",
]


def extract_ips_from_api(url):
    """
    从指定的URL获取IP。此函数内部包含了网络请求、JSON解析和数据处理的异常捕获。
    """
    local_cm, local_cu, local_ct = [], [], []

    try:
        # --- 3. 对网络请求进行异常处理 ---
        response = requests.get(url, timeout=10)  # 设置10秒超时
        response.raise_for_status()  # 如果状态码不是2xx，则抛出HTTPError异常

        # --- 4. 对JSON解析进行异常处理 ---
        data = response.json()

    except requests.exceptions.Timeout:
        print(f"【错误】: 请求API '{url}' 超时。")
        return [], [], []
    except requests.exceptions.HTTPError as e:
        print(f"【错误】: 请求API '{url}' 失败，HTTP状态码: {e.response.status_code}")
        return [], [], []
    except requests.exceptions.RequestException as e:
        print(f"【错误】: 请求API '{url}' 时发生网络错误: {e}")
        return [], [], []
    except json.JSONDecodeError:
        print(f"【错误】: 解析来自 '{url}' 的响应失败，内容不是有效的JSON格式。")
        return [], [], []

    # --- 5. 对数据结构进行健壮性处理 ---
    # 确保data['data']是一个字典，如果不是或不存在，.get()会返回一个空字典，避免程序出错
    ip_data = data.get("data")
    if not isinstance(ip_data, dict):
        print(f"【警告】: API响应中 'data' 字段的格式不正确（不是字典），无法提取IP。")
        return [], [], []

    all_ips_info = {}
    for provider_key, ips_list in ip_data.items():
        # 确保每个运营商对应的ips_list是列表类型
        if not isinstance(ips_list, list):
            continue  # 如果不是列表，就跳过这个运营商

        for ip_info in ips_list:
            # 确保ip_info是字典，并且包含'ip'键
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


# === 主要逻辑：现在每一步都有保护 ===

# 1. 从API获取IP (函数内部已处理异常)
print("--- 开始执行任务 ---")
print("步骤 1: 正在从 API 获取IP...")
cm_ip_api, cu_ip_api, ct_ip_api = extract_ips_from_api(API_URL)
print(f"API 获取完成。移动 {len(cm_ip_api)}, 联通 {len(cu_ip_api)}, 电信 {len(ct_ip_api)} 个IP")

# 2. 从v3data获取IP
print("\n步骤 2: 正在从 v3data 获取IP...")
try:
    # --- 2. 对v3data()函数执行进行异常处理 ---
    cm_ip_v3, cu_ip_v3, ct_ip_v3 = v3data()
    print(f"v3data 获取完成。移动 {len(cm_ip_v3)}, 联通 {len(cu_ip_v3)}, 电信 {len(ct_ip_v3)} 个IP")
except Exception as e:
    print(f"【错误】: 执行 v3data() 函数时发生意外: {e}。将跳过此数据源。")
    # 出错时，确保列表为空，以便后续合并操作能正常进行
    cm_ip_v3, cu_ip_v3, ct_ip_v3 = [], [], []

# 3. 合并结果 (这一步是安全的，因为所有列表都已确保存在)
print("\n步骤 3: 正在合并所有数据源...")
cm_ip_final = cm_ip_api + cm_ip_v3
cu_ip_final = cu_ip_api + cu_ip_v3
ct_ip_final = ct_ip_api + ct_ip_v3
print("合并完成。")

# === 输出最终结果 (这部分逻辑本身很安全) ===
print("\n--- 合并后的最终IP列表 ---")

# ... (输出部分的代码与之前相同，因为即使列表为空，它也能正常工作)
# --- 处理移动IP ---
print("\n移动IP列表:")
unique_cm_ips = sorted(list(set(cm_ip_final)))
print(f"合并去重后共: {len(unique_cm_ips)} 个")
if len(unique_cm_ips) > 50:
    print("列表超过50个，仅保留最后50个。")
    unique_cm_ips = unique_cm_ips[-50:]
for ip in unique_cm_ips:
    print(ip)
print(f"最终输出: {len(unique_cm_ips)} 个")

# --- 处理联通IP ---
print("\n联通IP列表:")
unique_cu_ips = sorted(list(set(cu_ip_final)))
print(f"合并去重后共: {len(unique_cu_ips)} 个")
if len(unique_cu_ips) > 50:
    print("列表超过50个，仅保留最后50个。")
    unique_cu_ips = unique_cu_ips[-50:]
for ip in unique_cu_ips:
    print(ip)
print(f"最终输出: {len(unique_cu_ips)} 个")

# --- 处理电信IP ---
print("\n电信IP列表:")
unique_ct_ips = sorted(list(set(ct_ip_final)))
print(f"合并去重后共: {len(unique_ct_ips)} 个")
if len(unique_ct_ips) > 50:
    print("列表超过50个，仅保留最后50个。")
    unique_ct_ips = unique_ct_ips[-50:]
for ip in unique_ct_ips:
    print(ip)
print(f"最终输出: {len(unique_ct_ips)} 个")

print("\n--- 任务执行完毕 ---")