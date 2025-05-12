import cloudscraper
import requests
from bs4 import BeautifulSoup
import re


# 初始化列表
cm_ip = []  # 移动IP
cu_ip = []  # 联通IP
ct_ip = []  # 电信IP
domain_list = [    # 泛播域名
    "store.epicgames.com",
    "cdnjs.com",
    "www.racknerd.com",
    "www.epicgames.com",
    "www.visa.com.tw",
    "qa.visamiddleeast.com",
    "cloudflare-ip.mofashi.ltd",
    "cf.877774.xyz",
    "fbi.gov",
    "www.wto.org",
    "www.fortnite.com",
    "ns3.cloudflare.com",
    "ns6.cloudflare.com",
    "ns4.cloudflare.com",
    "ns5.cloudflare.com",
    "radar.cloudflare.com",
]


def extract_table_values(url):
    """
    从指定的URL中提取表格数据，仅返回值。
    参数:
    - url: 网页的URL。
    返回:
    - 包含每行数据值的列表列表。
    """
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)
        response.raise_for_status()  # 检查请求是否成功
        html_content = response.text
    except Exception as e:
        print(f"请求失败: {e}")
        return []
    # 解析HTML内容
    soup = BeautifulSoup(html_content, 'html.parser')
    # 找到第一个表格
    table = soup.find('table')
    # 检查是否找到表格
    if not table:
        print("未找到表格")
        return []
    # 找到表格主体
    table_body = table.find('tbody')
    # 用于存储结果的列表
    results = []
    # 提取每一行的数据
    for row in table_body.find_all('tr'):
        cols = row.find_all('td')
        # 只提取需要的列值
        values = [
            cols[0].text.strip(),  # 线路名称
            cols[1].text.strip(),  # 优选地址
            cols[6].text.strip()  # 更新时间
        ]
        results.append(values)
    return results


def extract_ip_and_domain_from_json(url):
    """
    从指定的URL中提取IP地址和域名，并将它们分类为两个列表。

    参数:
    - url: API的URL。

    返回:
    - 包含IP地址的列表和包含域名的列表。
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查请求是否成功
        data = response.json()  # 解析JSON响应
    except Exception as e:
        print(f"请求失败: {e}")
        return [], []

    # 用于存储IP地址和域名的列表
    ip_list = []
    domain_list = []

    # 检查响应状态
    if data.get("status") == "success":
        for item in data.get("data", []):
            ip_or_domain = item.get("ip", "")

            # 使用正则表达式判断是否为IP地址
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_or_domain):
                ip_list.append(ip_or_domain)
            else:
                domain_list.append(ip_or_domain)

    return ip_list, domain_list


def extract_ips_from_third_site(url):
    """
    从指定的URL中提取第一个表格的前10个IP地址，并根据名称将其添加到相应的列表中。

    参数:
    - url: 网页的URL。

    返回:
    - 更新后的移动、联通和电信IP列表。
    """
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)
        response.raise_for_status()  # 检查请求是否成功
        html_content = response.text
    except Exception as e:
        print(f"请求失败: {e}")
        return [], [], []

    # 解析HTML内容
    soup = BeautifulSoup(html_content, 'html.parser')

    # 找到第一个表格
    table = soup.find('table')

    # 检查是否找到表格
    if table:
        # 初始化计数器
        cm_count = 0
        cu_count = 0
        ct_count = 0

        # 提取每一行的第一列和第二列数据
        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > 1:  # 确保有两列
                name = cols[0].text.strip()
                ip = cols[1].text.strip()

                # 根据名称将IP添加到相应的列表中
                if "移动" in name and cm_count < 10:
                    cm_ip.append(ip)
                    cm_count += 1
                elif "联通" in name and cu_count < 10:
                    cu_ip.append(ip)
                    cu_count += 1
                elif "电信" in name and ct_count < 10:
                    ct_ip.append(ip)
                    ct_count += 1
    else:
        print("未找到表格")

    return cm_ip, cu_ip, ct_ip


def extract_ips_from_fourth_site(url):
    """
    从指定的URL中提取IP地址，并将其添加到移动、联通和电信IP列表中。

    参数:
    - url: 网页的URL。

    返回:
    - 更新后的移动、联通和电信IP列表。
    """
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)
        response.raise_for_status()  # 检查请求是否成功
        ip_text = response.text.strip()  # 获取文本内容
    except Exception as e:
        print(f"请求失败: {e}")
        return [], [], []

    # 将文本内容分割成IP地址列表
    ip_list = ip_text.split(',')

    # 将IP地址添加到所有列表
    cm_ip.extend(ip_list)
    cu_ip.extend(ip_list)
    ct_ip.extend(ip_list)

    return cm_ip, cu_ip, ct_ip




# 1
data = extract_table_values("https://www.wetest.vip/page/cloudflare/address_v4.html")
for values in data:
    if "移动" in values[0]:
        cm_ip.append(values[1])
    elif "联通" in values[0]:
        cu_ip.append(values[1])
    elif "电信" in values[0]:
        ct_ip.append(values[1])

# 3
cm_ip, cu_ip, ct_ip = extract_ips_from_third_site("https://cf.090227.xyz")

# 4
cm_ip, cu_ip, ct_ip = extract_ips_from_fourth_site("https://ip.164746.xyz/ipTop10.html")



# 输出
print("移动IP列表:")
for ip in cm_ip:
    print(ip)
print("\n联通IP列表:")
for ip in cu_ip:
    print(ip)
print("\n电信IP列表:")
for ip in ct_ip:
    print(ip)
# print("\n域名列表:")#未处理
# for domain in domain_list:
#     print(domain)
