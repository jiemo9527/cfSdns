from __future__ import annotations

import binascii
import json
import logging
import time

import requests
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad

from .logging_utils import configure_logging


logger = logging.getLogger(__name__)

# 用于加密请求时间戳的密钥 (来自 JS 模块 5f87 的 O() 函数)
REQUEST_TOKEN_KEY = "385f33cb91484b04a177828829081ab7".encode("utf-8")

# 用于解密服务器响应 message 的密钥 (来自 JS 模块 5f87 的 T() 函数)
RESPONSE_MESSAGE_KEY = "125f33c891484b046777828569081a34".encode("utf-8")

IV = "00000000".encode("utf-8")
V3DATA_URL = "https://vps789.com/public/cfMonitorList"
V3DATA_TIMEOUT_SECONDS = 12
V3DATA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}
V3DATA_PAYLOAD = {
    "criteria": {
        "remarks": {"contains": "ip"},
        "allPkgLostRateAvg": {"lessThanOrEqual": ""},
    },
    "page": {
        "number": 1,
        "size": 400,
        "sort": ["createdTime,asc"],
    },
}
V3DATA_PACKET_LOSS_THRESHOLDS = {
    "mobile": 3.5,
    "unicom": 0.25,
    "telecom": 3.5,
}


def generate_request_token() -> str:
    """生成加密后的时间戳 token，用于请求头。"""
    timestamp_ms = str(int(time.time() * 1000)).encode("utf-8")
    cipher = DES.new(REQUEST_TOKEN_KEY[:8], DES.MODE_CBC, IV)
    padded_data = pad(timestamp_ms, DES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return encrypted_data.hex()


def decrypt_response_message(encrypted_hex_data: str) -> str:
    """解密服务器返回的加密 message。"""
    encrypted_data = binascii.unhexlify(encrypted_hex_data)
    cipher = DES.new(RESPONSE_MESSAGE_KEY[:8], DES.MODE_CBC, IV)
    decrypted_padded_data = cipher.decrypt(encrypted_data)
    decrypted_data = unpad(decrypted_padded_data, DES.block_size)
    return decrypted_data.decode("utf-8")


def build_request_headers() -> dict[str, str]:
    headers = dict(V3DATA_HEADERS)
    headers["token"] = generate_request_token()
    return headers


def fetch_v3data_response() -> dict[str, object]:
    logger.info("正在请求 v3data 数据源...")
    response = requests.post(
        V3DATA_URL,
        headers=build_request_headers(),
        json=V3DATA_PAYLOAD,
        timeout=V3DATA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def decode_v3data_message(response_json: dict[str, object]) -> dict[str, object]:
    if response_json.get("code") != 0:
        raise ValueError(f"API 返回错误: {response_json.get('message')}")

    encrypted_message = response_json.get("message")
    if not isinstance(encrypted_message, str) or not encrypted_message:
        raise ValueError("API 响应中缺少 message 字段")

    decrypted_text = decrypt_response_message(encrypted_message)
    return json.loads(decrypted_text)


def classify_v3data_ips(decoded_payload: dict[str, object]) -> tuple[list[str], list[str], list[str]]:
    carrier_ips = {"mobile": [], "unicom": [], "telecom": []}

    content = decoded_payload.get("content", [])
    if not isinstance(content, list):
        return carrier_ips["mobile"], carrier_ips["unicom"], carrier_ips["telecom"]

    for ip_info in content:
        if not isinstance(ip_info, dict):
            continue

        ip_address = ip_info.get("ip")
        if not ip_address:
            continue

        if ip_info.get("ydPkgLostRateAvg", float("inf")) < V3DATA_PACKET_LOSS_THRESHOLDS["mobile"]:
            carrier_ips["mobile"].append(ip_address)
        if ip_info.get("ltPkgLostRateAvg", float("inf")) < V3DATA_PACKET_LOSS_THRESHOLDS["unicom"]:
            carrier_ips["unicom"].append(ip_address)
        if ip_info.get("dxPkgLostRateAvg", float("inf")) < V3DATA_PACKET_LOSS_THRESHOLDS["telecom"]:
            carrier_ips["telecom"].append(ip_address)

    return carrier_ips["mobile"], carrier_ips["unicom"], carrier_ips["telecom"]


def v3data() -> tuple[list[str], list[str], list[str]]:
    try:
        response_json = fetch_v3data_response()
        logger.info("v3data 请求成功，开始解密响应...")
        decoded_payload = decode_v3data_message(response_json)
        return classify_v3data_ips(decoded_payload)
    except requests.exceptions.RequestException as exc:
        logger.warning("v3data 请求失败: %s", exc)
    except (ValueError, KeyError, json.JSONDecodeError, binascii.Error) as exc:
        logger.warning("v3data 解析失败: %s", exc)
    except Exception as exc:
        logger.warning("v3data 处理过程中发生错误: %s", exc)

    return [], [], []


if __name__ == "__main__":
    configure_logging(format_string="%(asctime)s - %(levelname)s - [V3Data] - %(message)s")
    cm_ip, cu_ip, ct_ip = v3data()
    logger.info("移动 %s 个，联通 %s 个，电信 %s 个。", len(cm_ip), len(cu_ip), len(ct_ip))
