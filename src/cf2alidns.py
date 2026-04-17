from __future__ import annotations

import json
import logging
from typing import Any

from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkcore.client import AcsClient

from .project_config import get_aliyun_credentials, get_package_num, load_runtime_env


DomainRecord = dict[str, Any]

load_runtime_env()
logger = logging.getLogger(__name__)
_client = None


def get_client():
    global _client

    if _client is not None:
        return _client

    access_key_id, access_key_secret = get_aliyun_credentials()
    if not access_key_id or not access_key_secret:
        logger.error("未能从环境变量中获取 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET。")
        return None

    _client = AcsClient(access_key_id, access_key_secret, "cn-hangzhou", timeout=15)
    return _client


def _build_describe_records_request(
    domain_name: str,
    page_number: int = 1,
    page_size: int = 500,
    subdomain: str | None = None,
    record_type: str | None = None,
):
    request = DescribeDomainRecordsRequest()
    request.set_accept_format("json")
    request.set_DomainName(domain_name)
    request.set_PageNumber(page_number)
    request.set_PageSize(page_size)
    if subdomain is not None:
        request.set_RRKeyWord(subdomain)
    if record_type is not None:
        request.set_Type(record_type)
    return request


def _build_add_record_request(domain_name: str, rr: str, record_type: str, value: str, line: str):
    request = AddDomainRecordRequest()
    request.set_accept_format("json")
    request.set_DomainName(domain_name)
    request.set_RR(rr)
    request.set_Type(record_type)
    request.set_Value(value)
    request.set_Line(line)
    return request


def _build_delete_record_request(record_id: str):
    request = DeleteDomainRecordRequest()
    request.set_RecordId(record_id)
    return request


def _execute_json_request(client, request) -> dict[str, Any]:
    response = client.do_action_with_exception(request)
    return json.loads(response)


def _filter_exact_rr_records(records: list[DomainRecord], subdomain: str | None) -> list[DomainRecord]:
    if subdomain is None:
        return records
    return [record for record in records if record.get("RR") == subdomain]


def _find_oldest_record(records: list[DomainRecord]) -> DomainRecord | None:
    if not records:
        return None
    return min(records, key=lambda record: record.get("CreateTimestamp", float("inf")))


def _find_matching_record(
    records: list[DomainRecord],
    rr: str,
    value: str,
    line: str,
    record_type: str = "A",
) -> DomainRecord | None:
    for record in records:
        if (
            record.get("RR") == rr
            and record.get("Value") == value
            and record.get("Line", "").lower() == line.lower()
            and record.get("Type") == record_type
        ):
            return record
    return None


def _index_records_by_line(existing_records: list[DomainRecord]) -> tuple[set[tuple[str, str]], dict[str, list[DomainRecord]], dict[str, int]]:
    existing_record_set = set()
    records_by_line: dict[str, list[DomainRecord]] = {}

    for record in existing_records:
        line_key = str(record.get("Line", "")).lower()
        value = str(record.get("Value", ""))
        if value and line_key:
            existing_record_set.add((value, line_key))
        records_by_line.setdefault(line_key, []).append(record)

    record_counts = {line_key: len(records) for line_key, records in records_by_line.items()}
    return existing_record_set, records_by_line, record_counts


def _delete_record_by_id(client, record_id: str) -> None:
    client.do_action_with_exception(_build_delete_record_request(record_id))


def _add_record_by_request(client, domain_name: str, rr: str, record_type: str, value: str, line: str) -> None:
    client.do_action_with_exception(_build_add_record_request(domain_name, rr, record_type, value, line))


def _ensure_line_capacity(
    client,
    line_key: str,
    carrier_line: str,
    package_num: int,
    records_by_line: dict[str, list[DomainRecord]],
    record_counts: dict[str, int],
) -> bool:
    current_count = record_counts.get(line_key, 0)
    if current_count < package_num:
        return True

    line_records = records_by_line.get(line_key, [])
    oldest_record = _find_oldest_record(line_records)
    if oldest_record is None:
        logger.warning("线路达到上限但未找到可删除记录: line=%s", carrier_line)
        return False

    _delete_record_by_id(client, oldest_record["RecordId"])
    line_records.remove(oldest_record)
    record_counts[line_key] = current_count - 1
    logger.info("为新增记录腾出空间，删除最旧记录: line=%s value=%s", carrier_line, oldest_record.get("Value"))
    return True


def query_all_domain_records(domain_name, subdomain=None):
    """查询并返回指定域名的记录。"""
    client = get_client()
    if not client:
        logger.error("AcsClient 未初始化，无法查询记录。")
        return []

    all_records = []
    page_number = 1
    page_size = 500

    while True:
        try:
            request = _build_describe_records_request(
                domain_name=domain_name,
                page_number=page_number,
                page_size=page_size,
                subdomain=subdomain,
            )
            response_json = _execute_json_request(client, request)
            records_on_page = response_json.get("DomainRecords", {}).get("Record", [])
            all_records.extend(_filter_exact_rr_records(records_on_page, subdomain))

            if len(records_on_page) < page_size:
                break

            page_number += 1
        except Exception as exc:
            logger.error("查询域名记录失败: domain=%s rr=%s error=%s", domain_name, subdomain, exc)
            break

    return all_records


def record_exists(domain_name, rr, record_type, value, line):
    """检查指定 DNS 记录是否已存在。"""
    client = get_client()
    if not client:
        return False

    try:
        request = _build_describe_records_request(domain_name=domain_name, subdomain=rr, record_type=record_type)
        response_json = _execute_json_request(client, request)
        records = _filter_exact_rr_records(response_json.get("DomainRecords", {}).get("Record", []), rr)
        return _find_matching_record(records, rr=rr, value=value, line=line, record_type=record_type) is not None
    except Exception as exc:
        logger.error(
            "检查记录是否存在失败: domain=%s rr=%s value=%s line=%s error=%s",
            domain_name,
            rr,
            value,
            line,
            exc,
        )
    return False


def delete_oldest_record(domain_name, rr, line):
    """查找并删除特定主机记录和线路的最早一条记录。"""
    client = get_client()
    if not client:
        return

    try:
        records = query_all_domain_records(domain_name)
        filtered_records = [record for record in records if record.get("RR") == rr and record.get("Line") == line]
        oldest_record = _find_oldest_record(filtered_records)
        if oldest_record is None:
            return

        _delete_record_by_id(client, oldest_record["RecordId"])
        logger.info("已删除最旧记录: rr=%s value=%s line=%s", rr, oldest_record.get("Value"), line)
    except Exception as exc:
        logger.error("删除最旧记录失败: domain=%s rr=%s line=%s error=%s", domain_name, rr, line, exc)


def add_record(domain_name, rr, record_type, value, line):
    """添加一条新的 DNS 记录，如果达到数量上限则删除最旧的记录。"""
    client = get_client()
    if not client:
        logger.error("AcsClient 未初始化，无法添加记录。")
        return

    package_num = get_package_num()

    try:
        if record_exists(domain_name, rr, record_type, value, line):
            return

        records = query_all_domain_records(domain_name=domain_name)
        count = sum(1 for record in records if record.get("RR") == rr and record.get("Line") == line)
        if count >= package_num:
            logger.warning("%s (%s) 的记录数量已达上限 (%s)，将删除最旧记录。", rr, line, package_num)
            delete_oldest_record(domain_name, rr, line)

        client.do_action_with_exception(_build_add_record_request(domain_name, rr, record_type, value, line))
        logger.info("成功添加记录: %s.%s | %s -> %s (%s)", rr, domain_name, record_type, value, line)
    except Exception as exc:
        logger.warning(
            "添加记录失败: domain=%s rr=%s type=%s value=%s line=%s error=%s",
            domain_name,
            rr,
            record_type,
            value,
            line,
            exc,
        )


def add_a_record(domain_name, rr, ip_addresses, line):
    """遍历 IP 地址列表，并将它们添加为 A 记录。"""
    for ip_address in ip_addresses:
        add_record(domain_name, rr, "A", ip_address, line)


def sync_aliyun_dns_records_exact(domain_rr: str, domain_root: str, ips_by_carrier: dict[str, list[str]]):
    """将指定 RR 的线路记录同步为目标集合，适合 temp 这类内部测速域名。"""
    client = get_client()
    if not all([domain_root, domain_rr, client]):
        logger.error("域名、主机记录或阿里云客户端未正确配置，中止精确同步。")
        return

    assert client is not None

    try:
        existing_records = query_all_domain_records(domain_root, subdomain=domain_rr)
    except Exception as exc:
        logger.error("获取现有 DNS 记录失败: rr=%s domain=%s error=%s", domain_rr, domain_root, exc)
        return

    logger.info("开始执行精确同步: rr=%s domain=%s", domain_rr, domain_root)
    for carrier_line, ip_list in ips_by_carrier.items():
        line_key = carrier_line.lower()
        desired_values = set(ip_list)
        line_records = [
            record
            for record in existing_records
            if record.get("Type") == "A" and str(record.get("Line", "")).lower() == line_key
        ]
        current_values = {str(record.get("Value", "")) for record in line_records}

        for record in line_records:
            record_value = str(record.get("Value", ""))
            if record_value and record_value not in desired_values:
                try:
                    _delete_record_by_id(client, record["RecordId"])
                    logger.info("删除 temp 旧记录: rr=%s line=%s value=%s", domain_rr, carrier_line, record_value)
                except Exception as exc:
                    logger.warning(
                        "删除 temp 旧记录失败: rr=%s line=%s value=%s error=%s",
                        domain_rr,
                        carrier_line,
                        record_value,
                        exc,
                    )

        for ip_address in sorted(desired_values - current_values):
            try:
                _add_record_by_request(client, domain_root, domain_rr, "A", ip_address, carrier_line)
                logger.info("新增 temp 记录: rr=%s line=%s value=%s", domain_rr, carrier_line, ip_address)
            except Exception as exc:
                logger.warning(
                    "新增 temp 记录失败: rr=%s line=%s value=%s error=%s",
                    domain_rr,
                    carrier_line,
                    ip_address,
                    exc,
                )

    logger.info("精确同步执行完毕: rr=%s domain=%s", domain_rr, domain_root)


def ensure_production_dns_records(
    domain_rr: str,
    domain_root: str,
    ips_by_carrier: dict[str, list[str]],
    floor_count: int,
    target_count: int,
    ceiling_count: int,
):
    """保守维护生产域名记录池，只补足到目标数量，不主动做大规模替换。"""
    client = get_client()
    if not all([domain_root, domain_rr, client]):
        logger.error("域名、主机记录或阿里云客户端未正确配置，中止生产池维护。")
        return

    assert client is not None

    try:
        existing_records = query_all_domain_records(domain_root, subdomain=domain_rr)
        existing_record_set, records_by_line, record_counts = _index_records_by_line(existing_records)
    except Exception as exc:
        logger.error("获取现有 DNS 记录失败: rr=%s domain=%s error=%s", domain_rr, domain_root, exc)
        return

    effective_target = min(target_count, ceiling_count)
    logger.info(
        "开始维护生产记录池: rr=%s domain=%s floor=%s target=%s ceiling=%s",
        domain_rr,
        domain_root,
        floor_count,
        effective_target,
        ceiling_count,
    )

    for carrier_line, ip_list in ips_by_carrier.items():
        line_key = carrier_line.lower()
        current_count = record_counts.get(line_key, 0)
        desired_candidates = [ip for ip in ip_list if (ip, line_key) not in existing_record_set]

        if current_count >= ceiling_count:
            logger.info("生产线路已达到上限，暂不新增: line=%s count=%s", carrier_line, current_count)
            continue

        logger.info("开始维护生产线路: line=%s current=%s candidates=%s", carrier_line, current_count, len(desired_candidates))
        for ip_address in desired_candidates:
            if current_count >= effective_target or current_count >= ceiling_count:
                break

            try:
                _add_record_by_request(client, domain_root, domain_rr, "A", ip_address, carrier_line)
                logger.info("新增生产记录: rr=%s line=%s value=%s", domain_rr, carrier_line, ip_address)
                existing_record_set.add((ip_address, line_key))
                records_by_line.setdefault(line_key, []).append({"Value": ip_address, "Line": carrier_line, "RR": domain_rr, "Type": "A"})
                current_count += 1
                record_counts[line_key] = current_count
            except Exception as exc:
                logger.warning(
                    "新增生产记录失败: rr=%s line=%s value=%s error=%s",
                    domain_rr,
                    carrier_line,
                    ip_address,
                    exc,
                )

        if current_count < floor_count:
            logger.warning("生产线路低于安全下限: line=%s current=%s floor=%s", carrier_line, current_count, floor_count)

    logger.info("生产记录池维护完毕: rr=%s domain=%s", domain_rr, domain_root)


def prune_production_dns_records(
    domain_rr: str,
    domain_root: str,
    preferred_ips_by_carrier: dict[str, list[str]],
    floor_count: int,
    ceiling_count: int,
    max_prune_per_line: int,
) -> list[dict[str, str]]:
    """当生产池超过 ceiling 时，温和删除本轮未入选且最旧的记录。"""
    client = get_client()
    if not all([domain_root, domain_rr, client]):
        logger.error("域名、主机记录或阿里云客户端未正确配置，中止生产池收敛。")
        return []

    assert client is not None

    try:
        existing_records = query_all_domain_records(domain_root, subdomain=domain_rr)
    except Exception as exc:
        logger.error("获取现有 DNS 记录失败: rr=%s domain=%s error=%s", domain_rr, domain_root, exc)
        return []

    pruned_records: list[dict[str, str]] = []
    for carrier_line, preferred_ips in preferred_ips_by_carrier.items():
        line_key = carrier_line.lower()
        line_records = [
            record
            for record in existing_records
            if record.get("Type") == "A" and str(record.get("Line", "")).lower() == line_key
        ]
        current_count = len(line_records)
        if current_count <= ceiling_count:
            continue

        protected_values = set(preferred_ips)
        deletable_records = sorted(
            [record for record in line_records if str(record.get("Value", "")) not in protected_values],
            key=lambda record: record.get("CreateTimestamp", float("inf")),
        )
        deletions_needed = min(current_count - ceiling_count, max_prune_per_line, max(current_count - floor_count, 0))

        if deletions_needed <= 0:
            continue

        for record in deletable_records[:deletions_needed]:
            record_value = str(record.get("Value", ""))
            if not record_value:
                continue

            try:
                _delete_record_by_id(client, record["RecordId"])
                pruned_records.append({"ip": record_value, "line": line_key})
                logger.info("收敛删除生产记录: rr=%s line=%s value=%s", domain_rr, carrier_line, record_value)
            except Exception as exc:
                logger.warning(
                    "收敛删除生产记录失败: rr=%s line=%s value=%s error=%s",
                    domain_rr,
                    carrier_line,
                    record_value,
                    exc,
                )

    return pruned_records


def update_aliyun_dns_records(domain_rr: str, domain_root: str, ips_by_carrier: dict[str, list[str]]):
    """先查询现有记录，再只对不存在的记录执行添加操作。"""
    client = get_client()
    package_num = get_package_num()

    logger.info("开始执行阿里云 DNS 更新流程: rr=%s domain=%s", domain_rr, domain_root)

    if not all([domain_root, domain_rr, client]):
        logger.error("域名、主机记录或阿里云客户端未正确配置，中止 DNS 更新。")
        return

    assert client is not None

    try:
        existing_records = query_all_domain_records(domain_root, subdomain=domain_rr)
        existing_record_set, records_by_line, record_counts = _index_records_by_line(existing_records)
        logger.info("找到 %s 条现有记录: rr=%s", len(existing_records), domain_rr)
    except Exception as exc:
        logger.error("获取现有 DNS 记录失败: rr=%s domain=%s error=%s", domain_rr, domain_root, exc)
        return

    for carrier_line, ip_list in ips_by_carrier.items():
        line_key = carrier_line.lower()
        if not ip_list:
            logger.info("线路 IP 列表为空，跳过: line=%s", carrier_line)
            continue

        logger.info("开始处理线路: line=%s count=%s", carrier_line, len(ip_list))
        for ip_address in ip_list:
            if (ip_address, line_key) in existing_record_set:
                continue

            try:
                if not _ensure_line_capacity(
                    client=client,
                    line_key=line_key,
                    carrier_line=carrier_line,
                    package_num=package_num,
                    records_by_line=records_by_line,
                    record_counts=record_counts,
                ):
                    continue

                client.do_action_with_exception(_build_add_record_request(domain_root, domain_rr, "A", ip_address, carrier_line))
                logger.info("成功添加记录: rr=%s ip=%s line=%s", domain_rr, ip_address, carrier_line)

                existing_record_set.add((ip_address, line_key))
                record_counts[line_key] = record_counts.get(line_key, 0) + 1
            except Exception as exc:
                logger.warning(
                    "添加记录失败: rr=%s domain=%s ip=%s line=%s error=%s",
                    domain_rr,
                    domain_root,
                    ip_address,
                    carrier_line,
                    exc,
                )

    logger.info("阿里云 DNS 更新流程执行完毕: rr=%s domain=%s", domain_rr, domain_root)


def delete_record_by_value(domain_name: str, rr: str, value: str, line: str):
    """根据记录值和线路删除一条指定的 A 记录。"""
    client = get_client()
    if not client:
        logger.error("AcsClient 未初始化，无法删除记录。")
        return

    try:
        records = query_all_domain_records(domain_name, subdomain=rr)
        record_to_delete = _find_matching_record(records, rr=rr, value=value, line=line, record_type="A")
        if record_to_delete is None:
            logger.warning("未找到要删除的记录: rr=%s value=%s line=%s", rr, value, line)
            return

        _delete_record_by_id(client, record_to_delete["RecordId"])
        logger.info(
            "成功删除记录: rr=%s value=%s line=%s record_id=%s",
            rr,
            value,
            line,
            record_to_delete["RecordId"],
        )
    except Exception as exc:
        logger.error("删除记录失败: rr=%s value=%s line=%s error=%s", rr, value, line, exc)
