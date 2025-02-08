from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
import json
import givemeCFIP

PackageNum=100 #套餐线路上限
# Access Key ID和Access Key Secret
client = AcsClient('', '', 'cn-hangzhou')

#查询并计算上限
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
            print(f"查询出错: {e}")
            break

    return all_records

#检测已存在
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
            if record['RR'] == rr and record['Type'] == record_type and record['Value'] == value and record['Line'] == line:
                return True
    except Exception as e:
        print(f"检测已存在出错: {e}")
    return False

#删除旧记录
def delete_oldest_record(domain_name, rr, line):
    try:
        records = query_all_domain_records(domain_name)
        filtered_records = [record for record in records if record['RR'] == rr and record['Line'] == line]
        if filtered_records:
            oldest_record = min(filtered_records, key=lambda x: x['CreateTimestamp'])
            request = DeleteDomainRecordRequest()
            request.set_RecordId(oldest_record['RecordId'])
            client.do_action_with_exception(request)
            print(f"删除记录: {oldest_record}")
    except Exception as e:
        print(f"删除旧记录出错: {e}")

#添加记录
def add_record(domain_name, rr, record_type, value, line):
    try:
        if record_exists(client, domain_name, rr, record_type, value, line):
            print(f"已存在的记录: {rr}.{domain_name} -> {value}({line})")
            return

        records = query_all_domain_records(domain_name)
        count = sum(1 for record in records if record['RR'] == rr and record['Line'] == line)

        if count >= 100:
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
        print(f"添加记录成功：{rr}.{domain_name}|{record_type} -> {value}({line})")
    except Exception as e:
        print(f"{rr}.{domain_name}|{record_type} -> {value}({line}: {e}")


#添加cname/a
def add_cname_record(domain_name, rr, cname_values, line):
    for cname_value in cname_values:
        add_record(domain_name, rr, 'CNAME', cname_value, line)
def add_a_record(domain_name, rr, ip_addresses, line, remark=None):
    for ip_address in ip_addresses:
        add_record(domain_name, rr, 'A', ip_address, line)

if __name__ == '__main__':
    xdomain = 'abc.com'
    # add_cname_record(xdomain, '@', givemeCFIP.domain_list, 'mobile')
    add_a_record(xdomain, 'x', givemeCFIP.cm_ip, 'mobile')
    add_a_record(xdomain, 'x', givemeCFIP.cu_ip, 'unicom')
    add_a_record(xdomain, 'x', givemeCFIP.ct_ip, 'telecom')
