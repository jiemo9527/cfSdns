import os
from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
import json
import logging

# 为此模块配置日志
logging.basicConfig(
    filename='./cf2alidns.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- 从环境变量中读取配置 ---
# 从环境变量中获取Access Key ID和Access Key Secret
access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
PackageNum = int(os.getenv('ALIYUN_PACKAGE_NUM', 100))  # 套餐允许的记录数量，默认为100
rr = os.getenv('domain_rr')  # 主机记录，例如 'www'
xdomain = os.getenv('domain_root')  # 主域名，例如 'example.com'

# 如果提供了凭据，则初始化AcsClient
client = None
if access_key_id and access_key_secret:
    client = AcsClient(access_key_id, access_key_secret, 'cn-hangzhou')
else:
    logging.error("未能从环境变量中获取 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET。")


# --- DNS辅助函数 ---

def query_all_domain_records(domain_name):
    """查询并返回指定域名的所有记录。"""
    if not client:
        logging.error("AcsClient未初始化，无法查询记录。")
        return []

    all_records = []
    page_number = 1
    page_size = 500

    while True:
        try:
            request = DescribeDomainRecordsRequest()
            request.set_accept_format('json')
            request.set_DomainName(domain_name)
            request.set_PageNumber(page_number)
            request.set_PageSize(page_size)

            response = client.do_action_with_exception(request)
            response_json = json.loads(response)

            records = response_json['DomainRecords']['Record']
            all_records.extend(records)

            total_count = response_json['TotalCount']
            if len(all_records) >= total_count:
                break

            page_number += 1
        except Exception as e:
            logging.error(f"查询域名记录时发生错误: {e}")
            break

    return all_records


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


def add_record(domain_name, rr, record_type, value, line):
    """添加一条新的DNS记录，如果达到数量上限则删除最旧的记录。"""
    if not client:
        logging.error("AcsClient未初始化，无法添加记录。")
        return

    try:
        if record_exists(domain_name, rr, record_type, value, line):
            logging.info(f"记录已存在，跳过添加: {rr}.{domain_name} -> {value} ({line})")
            return

        records = query_all_domain_records(domain_name)
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
        logging.error(f"添加记录失败 {rr}.{domain_name} -> {value} ({line}): {e}")


def add_a_record(domain_name, rr, ip_addresses, line):
    """遍历IP地址列表，并将它们添加为A记录。"""
    for ip_address in ip_addresses:
        add_record(domain_name, rr, 'A', ip_address, line)


# --- 本模块主功能函数 ---

def update_aliyun_dns_records(cm_ip: list, cu_ip: list, ct_ip: list):
    """
    使用提供的IP列表更新阿里云的A记录。

    参数:
        cm_ip (list): 用于“移动”线路的IP列表。
        cu_ip (list): 用于“联通”线路的IP列表。
        ct_ip (list): 用于“电信”线路的IP列表。
    """
    logging.info("开始执行阿里云DNS更新流程...")

    if not all([xdomain, rr, client]):
        logging.error("域名、主机记录或阿里云客户端未配置。中止DNS更新。")
        return

    logging.info(f"正在为 {rr}.{xdomain} 更新记录")

    logging.info(f"为 'mobile' (移动) 线路添加 {len(cm_ip)} 条记录...")
    add_a_record(xdomain, rr, cm_ip, 'mobile')

    logging.info(f"为 'unicom' (联通) 线路添加 {len(cu_ip)} 条记录...")
    add_a_record(xdomain, rr, cu_ip, 'unicom')

    logging.info(f"为 'telecom' (电信) 线路添加 {len(ct_ip)} 条记录...")
    add_a_record(xdomain, rr, ct_ip, 'telecom')

    logging.info("阿里云DNS更新流程执行完毕。")