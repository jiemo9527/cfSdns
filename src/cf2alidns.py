from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
import json
import logging
import os
from dotenv import load_dotenv
load_dotenv()


# 为此模块配置日志
logging.basicConfig(
    filename='./cf2alidns.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- 从环境变量中读取配置 ---
access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
PackageNum = int(os.getenv('ALIYUN_PACKAGE_NUM', 100))


# 如果提供了凭据，则初始化AcsClient
client = None
if access_key_id and access_key_secret:
    client = AcsClient(access_key_id, access_key_secret, 'cn-hangzhou')
else:
    logging.error("未能从环境变量中获取 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET。")


# 总查询 关键字查询
def query_all_domain_records(domain_name, subdomain=None):
    """
    查询并返回指定域名的记录。
    如果提供了subdomain，则只返回该精确子域名的记录。

    :param domain_name: 主域名, 例如 "example.com"
    :param subdomain: 子域名(主机记录RR), 例如 "www"。如果为None, 则查询所有记录。
                      注意：对于 'www.example.com'，此参数应传入 'www'。
                      对于根域名记录(例如 example.com 的A记录), 此参数应传入 '@'。
    :return: 包含DNS记录信息的字典列表
    """
    if not client:
        logging.error("AcsClient未初始化，无法查询记录。")
        return []

    all_records = []
    page_number = 1
    page_size = 500  # API允许的最大页面大小

    while True:
        try:
            request = DescribeDomainRecordsRequest()
            request.set_accept_format('json')
            request.set_DomainName(domain_name)
            request.set_PageNumber(page_number)
            request.set_PageSize(page_size)

            # 如果指定了子域名，则设置RRKeyWord参数进行筛选
            if subdomain is not None:
                request.set_RRKeyWord(subdomain)

            response_str = client.do_action_with_exception(request)
            response_json = json.loads(response_str)

            records_on_page = response_json['DomainRecords']['Record']

            # 如果是查询特定子域名，需要进行精确匹配过滤
            # 因为RRKeyWord是模糊搜索，例如搜索'test'会匹配到'test'和'test-api'
            if subdomain is not None:
                exact_match_records = [rec for rec in records_on_page if rec['RR'] == subdomain]
                all_records.extend(exact_match_records)
            else:
                # 如果不指定子域名，则添加所有记录
                all_records.extend(records_on_page)

            # 判断是否已获取所有记录
            # 如果当页返回的记录数小于请求的页面大小，说明已经是最后一页
            if len(records_on_page) < page_size:
                break

            page_number += 1

        except Exception as e:
            logging.error(f"查询域名记录时发生错误 (域名: {domain_name}, 子域名: {subdomain}): {e}")
            break

    return all_records

#查询记录
def record_exists(domain_name, rr, record_type, value, line):
    """检查指定的DNS记录是否已存在。"""
    if not client:
        return False

    try:
        request = DescribeDomainRecordsRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain_name)
        request.set_RRKeyWord(rr)
        request.set_Type(record_type)

        response = client.do_action_with_exception(request)
        response_json = json.loads(response)

        for record in response_json.get('DomainRecords', {}).get('Record', []):
            if record['RR'] == rr and record['Type'] == record_type and record['Value'] == value and record[
                'Line'] == line:
                return True
    except Exception as e:
        logging.error(f"检查记录是否存在时出错: {e}")
    return False

#子功能1
def delete_oldest_record(domain_name, rr, line):
    """查找并删除特定主机记录（RR）和线路的最早一条记录。"""
    if not client:
        return

    try:
        records = query_all_domain_records(domain_name)
        filtered_records = [record for record in records if record['RR'] == rr and record['Line'] == line]
        if filtered_records:
            oldest_record = min(filtered_records, key=lambda x: x.get('CreateTimestamp', float('inf')))
            request = DeleteDomainRecordRequest()
            request.set_RecordId(oldest_record['RecordId'])
            client.do_action_with_exception(request)
            logging.info(f"已删除最旧的记录: {oldest_record}")
    except Exception as e:
        logging.error(f"删除最旧记录时出错: {e}")

#子功能2
def add_record(domain_name, rr, record_type, value, line):
    """添加一条新的DNS记录，如果达到数量上限则删除最旧的记录。"""
    if not client:
        logging.error("AcsClient未初始化，无法添加记录。")
        return

    try:
        if record_exists(domain_name, rr, record_type, value, line):
            logging.info(f"记录已存在，跳过添加: {rr}.{domain_name} -> {value} ({line})")
            return

        records = query_all_domain_records(domain_name=domain_name)
        count = sum(1 for record in records if record['RR'] == rr and record['Line'] == line)

        if count >= PackageNum:
            logging.warning(f"{rr} ({line}) 的记录数量已达上限 ({PackageNum})。正在删除最旧的记录。")
            delete_oldest_record(domain_name, rr, line)

        request = AddDomainRecordRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain_name)
        request.set_RR(rr)
        request.set_Type(record_type)
        request.set_Value(value)
        request.set_Line(line)

        client.do_action_with_exception(request)
        logging.info(f"成功添加记录: {rr}.{domain_name} | {record_type} -> {value} ({line})")
    except Exception as e:
        pass
        # logging.warning(f"添加记录失败 {rr}.{domain_name} -> {value} ({line}): {e}")

#子功能3
def add_a_record(domain_name, rr, ip_addresses, line):
    """遍历IP地址列表，并将它们添加为A记录。"""
    for ip_address in ip_addresses:
        add_record(domain_name, rr, 'A', ip_address, line)


#合并功能
def update_aliyun_dns_records(domain_rr: str, domain_root: str, ips_by_carrier: dict):
    """
    使用提供的IP字典更新阿里云的A记录（重构后的灵活版本）。

    参数:
        domain_rr (str): 主机记录 (例如 'www', 'temp').
        domain_root (str): 主域名 (例如 'example.com').
        ips_by_carrier (dict): 一个包含IP列表的字典。
                               格式: {'线路名称': ['ip1', 'ip2'], ...}
                               示例: {'mobile': ['1.1.1.1'], 'telecom': ['8.8.8.8']}
    """
    logging.info("开始执行阿里云DNS更新流程...")

    if not all([domain_root, domain_rr, client]):
        logging.error("域名、主机记录或阿里云客户端未正确配置。中止DNS更新。")
        return

    logging.info(f"正在为 {domain_rr}.{domain_root} 更新记录")

    # 遍历传入的字典，动态地为每个运营商（线路）更新记录
    for carrier_line, ip_list in ips_by_carrier.items():
        # 如果某个运营商的IP列表为空，则跳过
        if not ip_list:
            logging.info(f"线路 '{carrier_line}' 的IP列表为空，跳过更新。")
            continue

        logging.info(f"为 '{carrier_line}' 线路添加 {len(ip_list)} 条记录...")
        add_a_record(domain_root, domain_rr, ip_list, carrier_line)

    logging.info("阿里云DNS更新流程执行完毕。")


#删除记录
def delete_record_by_value(domain_name: str, rr: str, value: str, line: str):
    """
    根据记录值（IP地址）和线路删除一条指定的A记录。

    :param domain_name: 主域名
    :param rr: 主机记录
    :param value: 记录值 (IP地址)
    :param line: 线路 ('telecom', 'unicom', 'mobile')
    """
    if not client:
        logging.error("AcsClient未初始化，无法删除记录。")
        return

    try:
        # 查询特定子域名的所有记录以找到匹配项
        records = query_all_domain_records(domain_name, subdomain=rr)
        record_to_delete = None
        for record in records:
            # 精确匹配 主机记录, IP地址, 线路, 和类型(A记录)
            if record['RR'] == rr and record['Value'] == value and record['Line'].lower() == line.lower() and record['Type'] == 'A':
                record_to_delete = record
                break

        if record_to_delete:
            record_id = record_to_delete['RecordId']
            request = DeleteDomainRecordRequest()
            request.set_RecordId(record_id)
            client.do_action_with_exception(request)
            logging.info(f"成功删除记录: RR={rr}, Value={value}, Line={line}, RecordId={record_id}")
        else:
            logging.warning(f"未找到要删除的记录: RR={rr}, Value={value}, Line={line}")

    except Exception as e:
        logging.error(f"删除记录时发生错误 (RR={rr}, Value={value}, Line={line}): {e}")