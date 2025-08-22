#某站js逆向解密
import requests
import json
import time
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad
import binascii

# --- 1. 定义所有常量 ---

# 用于加密请求时间戳的密钥 (来自JS模块 5f87 的 O() 函数)
REQUEST_TOKEN_KEY = "385f33cb91484b04a177828829081ab7".encode('utf-8')

# 用于解密服务器响应message的密钥 (来自JS模块 5f87 的 T() 函数)
RESPONSE_MESSAGE_KEY = "125f33c891484b046777828569081a34".encode('utf-8')

# 初始向量 (IV)，两者通用
IV = "00000000".encode('utf-8')


# --- 2. 定义辅助函数 ---

def generate_request_token():
    """
    生成加密后的时间戳 token，用于请求头。
    """
    timestamp_ms = str(int(time.time() * 1000)).encode('utf-8')
    cipher = DES.new(REQUEST_TOKEN_KEY[:8], DES.MODE_CBC, IV)
    padded_data = pad(timestamp_ms, DES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return encrypted_data.hex()


def decrypt_response_message(encrypted_hex_data):
    """
    解密服务器返回的加密 message。
    """
    encrypted_data = binascii.unhexlify(encrypted_hex_data)
    cipher = DES.new(RESPONSE_MESSAGE_KEY[:8], DES.MODE_CBC, IV)
    decrypted_padded_data = cipher.decrypt(encrypted_data)
    decrypted_data = unpad(decrypted_padded_data, DES.block_size)
    return decrypted_data.decode('utf-8')


# --- 3. 主程序：请求和解密 ---

# 定义请求URL、头和载荷
url = "https://vps789.com/public/cfMonitorList"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'Content-Type': 'application/json'
}
payload = {
    "criteria": {
        "remarks": {"contains": "ip"},
        "allPkgLostRateAvg": {"lessThanOrEqual": ""}
    },
    "page": {
        "number": 1,
        "size": 400,
        "sort": ["createdTime,asc"]
    }
}
def v3data():
    try:
        # 动态生成并添加 token
        headers['token'] = generate_request_token()

        # 发送POST请求
        print("正在发送请求...")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        response_json = response.json()
        print("请求成功，正在解密...")

        # 检查响应码并提取加密的message
        if response_json.get("code") == 0:
            encrypted_message = response_json.get("message")
            if encrypted_message:
                # 解密 message
                decrypted_text = decrypt_response_message(encrypted_message)
                final_data = json.loads(decrypted_text)

                # --- 新增：数据筛选 ---
                print("\n---------- 开始筛选数据... ----------")
                cm_ip = []
                cu_ip = []
                ct_ip = []

                # 遍历解密后数据中的 'content' 列表
                for ip_info in final_data.get('content', []):
                    ip = ip_info.get("ip")
                    if not ip:
                        continue  # 如果没有IP信息，跳过

                    yd_loss = ip_info.get("ydPkgLostRateAvg", float('inf'))
                    lt_loss = ip_info.get("ltPkgLostRateAvg", float('inf'))
                    dx_loss = ip_info.get("dxPkgLostRateAvg", float('inf'))

                    # 只要满足移动的条件，就添加到移动列表
                    if yd_loss < 3.5:
                        cm_ip.append(ip)

                    # 只要满足联通的条件，就添加到联通列表
                    if lt_loss < 0.5:
                        cu_ip.append(ip)

                    # 只要满足电信的条件，就添加到电信列表
                    if dx_loss < 3.5:
                        ct_ip.append(ip)

                # print("\n---------- 筛选完成！结果如下 ----------")
                # print(f"移动 (CM) 线路: 共 {len(cm_ip)} 个")
                # print(cm_ip)
                # print(f"\n联通 (CU) 线路: 共 {len(cu_ip)} 个")
                # print(cu_ip)
                # print(f"\n电信 (CT) 线路: 共 {len(ct_ip)} 个")
                # print(ct_ip)
                return cm_ip, cu_ip, ct_ip

        else:
            print(f"\nAPI返回错误，消息: {response_json.get('message')}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except Exception as e:
        print(f"处理过程中发生错误: {e}")