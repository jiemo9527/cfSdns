import os

from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
import json
import givemeCFIP
import logging

# 配置日志
logging.basicConfig(
    filename='/app/cf2alidns.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# PackageNum=100 #套餐线路上限
# client = AcsClient('Key', 'Secret', 'cn-hangzhou')

# 从环境变量中获取 Access Key ID 和 Access Key Secret
access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
PackageNum = int(os.getenv('ALIYUN_PACKAGE_NUM', 100))  # 默认值为 100
rr = os.getenv('domain_rr')
xdomain = os.getenv('domain_root')

# 初始化 AcsClient
client = AcsClient(access_key_id, access_key_secret, 'cn-hangzhou')


# 查询并计算上限
def query_all_domain_records(domain_name):
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
            total_pages = (total_count + page_size - 1) // page_size

            if page_number >= total_pages:
                break

            page_number += 1
        except Exception as e:
            logging.error(f"查询出错: {e}")
            break

    return all_records


# 检测已存在
def record_exists(client, domain_name, rr, record_type, value, line):
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
        logging.error(f"检测已存在出错: {e}")
    return False


# 删除旧记录
def delete_oldest_record(domain_name, rr, line):
    try:
        records = query_all_domain_records(domain_name)
        filtered_records = [record for record in records if record['RR'] == rr and record['Line'] == line]
        if filtered_records:
            oldest_record = min(filtered_records, key=lambda x: x['CreateTimestamp'])
            request = DeleteDomainRecordRequest()
            request.set_RecordId(oldest_record['RecordId'])
            client.do_action_with_exception(request)
            logging.info(f"删除记录: {oldest_record}")
    except Exception as e:
        logging.error(f"删除旧记录出错: {e}")


# 添加记录
def add_record(domain_name, rr, record_type, value, line):
    try:
        if record_exists(client, domain_name, rr, record_type, value, line):
            logging.info(f"已存在的记录: {rr}.{domain_name} -> {value}({line})")
            return

        records = query_all_domain_records(domain_name)
        count = sum(1 for record in records if record['RR'] == rr and record['Line'] == line)

        if count >= PackageNum:
            delete_oldest_record(domain_name, rr, line)

        request = AddDomainRecordRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain_name)
        request.set_RR(rr)
        request.set_Type(record_type)
        request.set_Value(value)
        request.set_Line(line)

        response = client.do_action_with_exception(request)
        response_json = json.loads(response)
        logging.info(f"添加记录成功：{rr}.{domain_name}|{record_type} -> {value}({line})")
    except Exception as e:
        logging.error(f"{rr}.{domain_name}|{record_type} -> {value}({line}: {e}")


# 添加cname/a
def add_cname_record(domain_name, rr, cname_values, line):
    for cname_value in cname_values:
        add_record(domain_name, rr, 'CNAME', cname_value, line)


def add_a_record(domain_name, rr, ip_addresses, line, remark=None):
    for ip_address in ip_addresses:
        add_record(domain_name, rr, 'A', ip_address, line)


if __name__ == '__main__':
    logging.info('start!')
    # xdomain = 'abc.com'
    # rr='x'
    # add_cname_record(xdomain, '@', givemeCFIP.domain_list, 'mobile')
    ct_ip, cm_ip, cu_ip  = givemeCFIP.get_cf_ips()
    add_a_record(xdomain, rr,cm_ip, 'mobile')
    add_a_record(xdomain, rr,cu_ip, 'unicom')
    add_a_record(xdomain, rr,ct_ip, 'telecom')
