from __future__ import annotations

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "src"

import ipaddress
import logging
import random
import re
import socket
from typing import List, Mapping, Tuple

import cloudscraper
import requests
from bs4 import BeautifulSoup

from .getv3data import v3data
from .logging_utils import configure_logging
from .project_constants import (
    EXCLUDED_IP_PREFIXES,
    IP_SOURCE_URLS,
    MAX_CANDIDATE_IPS_PER_CARRIER,
    MAX_CF090227_IPS_PER_CARRIER,
    PUBLIC_DOH_ENDPOINTS,
)


logger = logging.getLogger(__name__)
IPV4_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _is_public_ipv4(ip_address: str) -> bool:
    if not IPV4_PATTERN.match(ip_address):
        return False

    try:
        return ipaddress.ip_address(ip_address).is_global
    except ValueError:
        return False


def _filter_candidate_ips(ip_addresses: List[str]) -> List[str]:
    filtered_ips = []
    for ip_address in ip_addresses:
        if not _is_public_ipv4(ip_address):
            continue
        if any(ip_address.startswith(prefix) for prefix in EXCLUDED_IP_PREFIXES):
            continue
        filtered_ips.append(ip_address)
    return filtered_ips


def _select_sample(ip_addresses: List[str], limit: int) -> List[str]:
    unique_ips = sorted(set(_filter_candidate_ips(ip_addresses)))
    if len(unique_ips) <= limit:
        return unique_ips
    return random.sample(unique_ips, limit)


def _resolve_ipv4_records_via_doh(hostname: str) -> List[str]:
    headers = {"accept": "application/dns-json"}

    for endpoint in PUBLIC_DOH_ENDPOINTS:
        try:
            response = requests.get(
                endpoint,
                params={"name": hostname, "type": "A"},
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            response_json = response.json()
            resolved_ips = [
                answer.get("data", "")
                for answer in response_json.get("Answer", [])
                if answer.get("type") == 1 and _is_public_ipv4(answer.get("data", ""))
            ]
            if resolved_ips:
                return sorted(set(resolved_ips))
        except Exception as exc:
            logger.warning("DoH 解析失败: host=%s endpoint=%s error=%s", hostname, endpoint, exc)

    try:
        resolved_ips = sorted(
            {
                str(result[4][0])
                for result in socket.getaddrinfo(hostname, None, socket.AF_INET)
                if _is_public_ipv4(str(result[4][0]))
            }
        )
        return resolved_ips
    except Exception as exc:
        logger.warning("本机 DNS 解析失败: host=%s error=%s", hostname, exc)
        return []


def _extract_host_from_tcping_link(link: str | None) -> str | None:
    marker = "/tcping/"
    if not link:
        return None
    if marker not in link:
        return None

    host_port = link.split(marker, 1)[1]
    if ":" in host_port:
        return host_port.rsplit(":", 1)[0].strip()
    return host_port.strip()


def _get_cf090227_carriers(card_text: str) -> List[str]:
    if "三网优选" in card_text:
        return ["mobile", "unicom", "telecom"]

    carriers = []
    if "移动" in card_text:
        carriers.append("mobile")
    if "联通" in card_text:
        carriers.append("unicom")
    if "电信" in card_text:
        carriers.append("telecom")

    return carriers or ["mobile", "unicom", "telecom"]


def classify_api_ip_data(data: Mapping[str, object]) -> Tuple[List[str], List[str], List[str]]:
    local_cm, local_cu, local_ct = [], [], []
    ip_data = data.get("data", {}) if isinstance(data, dict) else {}
    if not isinstance(ip_data, dict):
        return local_cm, local_cu, local_ct

    all_ips_info = {}
    for provider_ips in ip_data.values():
        if not isinstance(provider_ips, list):
            continue
        for ip_info in provider_ips:
            if isinstance(ip_info, dict) and "ip" in ip_info:
                all_ips_info[ip_info["ip"]] = ip_info

    for ip_address, ip_info in all_ips_info.items():
        if not _is_public_ipv4(ip_address):
            continue
        if ip_info.get("ydPkgLostRateAvg", 100) < 3.5:
            local_cm.append(ip_address)
        if ip_info.get("ltPkgLostRateAvg", 100) < 0.5:
            local_cu.append(ip_address)
        if ip_info.get("dxPkgLostRateAvg", 100) < 3.5:
            local_ct.append(ip_address)

    return local_cm, local_cu, local_ct


def parse_table_ips_from_html(html: str) -> Tuple[List[str], List[str], List[str]]:
    cm_ips, cu_ips, ct_ips = [], [], []
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return [], [], []

    for row in table.find_all("tr"):
        columns = row.find_all("td")
        if len(columns) <= 1:
            continue

        carrier_name = columns[0].get_text(strip=True)
        ip_address = columns[1].get_text(strip=True)
        if not _is_public_ipv4(ip_address):
            continue

        if "移动" in carrier_name:
            cm_ips.append(ip_address)
        elif "联通" in carrier_name:
            cu_ips.append(ip_address)
        elif "电信" in carrier_name:
            ct_ips.append(ip_address)

    return cm_ips, cu_ips, ct_ips


def parse_text_ips(text: str) -> List[str]:
    return [ip.strip() for ip in text.split(",") if _is_public_ipv4(ip.strip())]


def parse_cf090227_domain_cards(html: str) -> list[tuple[str, list[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    parsed_cards = []

    for card in soup.select(".domain-card"):
        card_text = " ".join(card.get_text(" ", strip=True).split())
        test_link = card.select_one(".test-link")
        if not test_link:
            continue

        host = _extract_host_from_tcping_link(test_link.get("href", ""))
        if not host:
            continue

        parsed_cards.append((host, _get_cf090227_carriers(card_text)))

    return parsed_cards


def extract_ips_from_api(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从 API 接口获取 IP，并根据丢包率筛选。"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("请求 API 失败: url=%s error=%s", url, exc)
        return [], [], []

    return classify_api_ip_data(data)


def extract_table_ips_from_html(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从 HTML 页面表格中提取 IP，并按运营商分类。"""
    cm_ips, cu_ips, ct_ips = [], [], []
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        return parse_table_ips_from_html(response.text)
    except Exception as exc:
        logger.warning("提取表格 IP 失败: url=%s error=%s", url, exc)
        return [], [], []


def extract_ips_from_text(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从纯文本页面提取逗号分隔的 IP 地址。"""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        ip_list = parse_text_ips(response.text)
        return ip_list, ip_list, ip_list
    except Exception as exc:
        logger.warning("提取纯文本 IP 失败: url=%s error=%s", url, exc)
        return [], [], []


def extract_ips_from_cf090227(url: str) -> Tuple[List[str], List[str], List[str]]:
    """从 cf.090227.xyz 的域名卡片中提取域名，并通过公共 DoH 解析出 A 记录。"""
    carrier_ips = {"mobile": [], "unicom": [], "telecom": []}
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("请求 cf.090227.xyz 失败: url=%s error=%s", url, exc)
        return [], [], []

    for host, carriers in parse_cf090227_domain_cards(response.text):
        resolved_ips = _resolve_ipv4_records_via_doh(host)
        if not resolved_ips:
            logger.info("cf.090227.xyz 域名未解析到公网 IPv4: host=%s", host)
            continue

        for carrier in carriers:
            carrier_ips[carrier].extend(resolved_ips)

    return (
        _select_sample(carrier_ips["mobile"], MAX_CF090227_IPS_PER_CARRIER),
        _select_sample(carrier_ips["unicom"], MAX_CF090227_IPS_PER_CARRIER),
        _select_sample(carrier_ips["telecom"], MAX_CF090227_IPS_PER_CARRIER),
    )


def get_cf_ips() -> Tuple[List[str], List[str], List[str]]:
    """执行获取、合并和处理 Cloudflare IP 的完整流程。"""
    all_cm_ips, all_cu_ips, all_ct_ips = [], [], []

    try:
        v3data_result = v3data()
        if not v3data_result:
            raise ValueError("v3data 未返回可用结果")

        cm_ip_v3, cu_ip_v3, ct_ip_v3 = v3data_result
        all_cm_ips.extend(cm_ip_v3)
        all_cu_ips.extend(cu_ip_v3)
        all_ct_ips.extend(ct_ip_v3)
        logger.info(
            "v3data 获取完成。移动 %s, 联通 %s, 电信 %s 个IP。",
            len(cm_ip_v3),
            len(cu_ip_v3),
            len(ct_ip_v3),
        )
    except Exception as exc:
        logger.warning("执行 v3data() 失败: %s", exc)

    source_extractors = [
        ("api.uouin.com", lambda: extract_table_ips_from_html(IP_SOURCE_URLS["uouin"])),
        ("wetest.vip", lambda: extract_table_ips_from_html(IP_SOURCE_URLS["wetest"])),
        ("cf.090227.xyz", lambda: extract_ips_from_cf090227(IP_SOURCE_URLS["cf090227"])),
        ("ip.164746.xyz", lambda: extract_ips_from_text(IP_SOURCE_URLS["ip164746"])),
    ]

    for source_name, extractor in source_extractors:
        cm_ips, cu_ips, ct_ips = extractor()
        all_cm_ips.extend(cm_ips)
        all_cu_ips.extend(cu_ips)
        all_ct_ips.extend(ct_ips)
        if source_name == "ip.164746.xyz":
            logger.info("%s 获取完成。共 %s 个IP。", source_name, len(cm_ips))
        else:
            logger.info(
                "%s 获取完成。移动 %s, 联通 %s, 电信 %s 个IP。",
                source_name,
                len(cm_ips),
                len(cu_ips),
                len(ct_ips),
            )

    final_ct_ip = _select_sample(all_ct_ips, MAX_CANDIDATE_IPS_PER_CARRIER)
    final_cm_ip = _select_sample(all_cm_ips, MAX_CANDIDATE_IPS_PER_CARRIER)
    final_cu_ip = _select_sample(all_cu_ips, MAX_CANDIDATE_IPS_PER_CARRIER)

    logger.info(
        "处理后：电信 %s 个, 移动 %s 个, 联通 %s 个。",
        len(final_ct_ip),
        len(final_cm_ip),
        len(final_cu_ip),
    )
    logger.info("IP 获取任务执行完毕。")
    return final_ct_ip, final_cm_ip, final_cu_ip


if __name__ == "__main__":
    configure_logging(format_string="%(asctime)s - %(levelname)s - [IPSource] - %(message)s")
    ct_ip, cm_ip, cu_ip = get_cf_ips()
    logger.info("最终获取到的 IP 列表：")
    logger.info("电信IP (%s个): %s", len(ct_ip), ct_ip)
    logger.info("移动IP (%s个): %s", len(cm_ip), cm_ip)
    logger.info("联通IP (%s个): %s", len(cu_ip), cu_ip)
