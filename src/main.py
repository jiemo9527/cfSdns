# -*- coding: utf-8 -*-
import asyncio
import os
import random
import time
from dotenv import load_dotenv
import getIPFromW3
import webTestUnion
import cf2alidns
import logging
import json

load_dotenv()

# 从环境变量加载配置
domain_rr = os.getenv('domain_rr')
domain_root = os.getenv('domain_root')
temp_subdomain = 'temp'


def filter_and_select_ips(json_string: str, count_per_carrier: int) -> dict:
    """
    从IT-Dog的JSON测试结果中为每个运营商分别筛选IP。
    """
    if not json_string:
        return {}
    try:
        results = json.loads(json_string)
    except json.JSONDecodeError:
        logging.error("解析测速结果JSON时出错。")
        return {}
    qualified_ips = {"mobile": [], "unicom": [], "telecom": []}
    for item in results:
        detection_point = item.get("检测点", "")
        status = item.get("状态", "")
        total_time_str = item.get("总耗时", "")
        ip_address = item.get("响应IP", "")
        if not ip_address or ip_address == "解析失败" or status != "530":
            continue
        is_time_ok = False
        if isinstance(total_time_str, str) and total_time_str.endswith('s'):
            try:
                time_val = float(total_time_str[:-1])
                if time_val < 1.0:
                    is_time_ok = True
            except (ValueError, TypeError):
                continue
        if is_time_ok:
            if detection_point.startswith("移动"):
                qualified_ips["mobile"].append(ip_address)
            elif detection_point.startswith("联通"):
                qualified_ips["unicom"].append(ip_address)
            elif detection_point.startswith("电信"):
                qualified_ips["telecom"].append(ip_address)
    final_selection = {}
    for carrier, ips in qualified_ips.items():
        unique_ips = sorted(list(set(ips)))
        if len(unique_ips) > count_per_carrier:
            selected = random.sample(unique_ips, count_per_carrier)
        else:
            selected = unique_ips
        final_selection[carrier] = selected
    return final_selection


def main():
    """
    主函数，用于执行从获取Cloudflare IP到更新阿里云DNS的完整流程。
    """
    logging.info("@@@@@ 开始一次完整的IP筛选与更新任务 @@@@@")

    # 准备工作：为确保环境干净，先删除 temp 子域名的所有记录
    logging.info(f"正在清理临时域名 {temp_subdomain}.{domain_root} 的旧记录...")
    existing_temp_records = cf2alidns.query_all_domain_records(domain_root, subdomain=temp_subdomain)
    if existing_temp_records:
        for record in existing_temp_records:
            # 直接使用 delete_record_by_value 更安全
            cf2alidns.delete_record_by_value(domain_root, temp_subdomain, record['Value'], record['Line'])
        logging.info(f"临时域名 {len(existing_temp_records)} 条旧记录清理完成。")
    else:
        logging.info("临时域名无旧记录，无需清理。")

    # 步骤1：获取IP源
    logging.info("步骤1：开始从所有来源获取IP...")
    ct_ip, cm_ip, cu_ip = getIPFromW3.get_cf_ips()
    logging.info(f"IP获取完成。移动: {len(cm_ip)}, 联通: {len(cu_ip)}, 电信: {len(ct_ip)}")

    # 步骤2：更新临时域名并进行第一次测速
    logging.info(f"步骤2：正在将IP更新到临时域名 {temp_subdomain}.{domain_root} 以进行测速...")
    # 【关键修改】将IP列表打包成字典
    initial_ips_dict = {
        'mobile': cm_ip,
        'unicom': cu_ip,
        'telecom': ct_ip
    }
    # 使用正确的参数名 ips_by_carrier 调用函数
    cf2alidns.update_aliyun_dns_records(domain_rr=temp_subdomain, domain_root=domain_root,
                                        ips_by_carrier=initial_ips_dict)

    logging.info("等待30秒以便临时域名DNS生效...")
    time.sleep(30)

    json_temp = asyncio.run(
        webTestUnion.run_itdog_test(target_host=f"{temp_subdomain}.{domain_root}", custom_dns="119.29.29.29"))
    if not json_temp:
        logging.error("第一次IT-Dog测速失败，程序中止。")
        return

    # 步骤3：筛选优质IP
    logging.info("步骤3：第一次测速完成，开始筛选优质IP...")
    selected_ips_by_carrier = filter_and_select_ips(json_temp, 5)

    if not any(selected_ips_by_carrier.values()):
        logging.warning("未能从第一次测速结果中筛选出任何符合条件的IP，程序中止。")
        return

    logging.info("成功筛选出各线路的随机优质IP:")
    for carrier, ips in selected_ips_by_carrier.items():
        carrier_name_cn = {"mobile": "移动", "unicom": "联通", "telecom": "电信"}
        print(f"--- {carrier_name_cn[carrier]} ({len(ips)}个) ---")
        print(ips)

    # 步骤4：更新生产域名
    logging.info(f"步骤4：正在将筛选出的优质IP更新到生产域名 {domain_rr}.{domain_root} ...")
    # 【关键修改】直接传递筛选结果的字典
    cf2alidns.update_aliyun_dns_records(domain_rr=domain_rr, domain_root=domain_root,
                                        ips_by_carrier=selected_ips_by_carrier)
    logging.info("生产域名DNS更新完成。")

    # 步骤5：第二次测速（验证）并剔除不良记录
    logging.info("步骤5：等待60秒以便生产域名DNS生效，准备进行最终验证...")
    time.sleep(60)

    json_validate = asyncio.run(
        webTestUnion.run_itdog_test(target_host=f"{domain_rr}.{domain_root}", custom_dns="223.5.5.5"))

    if json_validate:
        logging.info("最终验证测速完成，开始检查并删除不良DNS记录...")
        try:
            results = json.loads(json_validate)
            records_to_delete = []
            carrier_map = {"电信": "telecom", "移动": "mobile", "联通": "unicom"}

            for item in results:
                status = item.get("状态", "")
                total_time_str = item.get("总耗时", "")
                ip_address = item.get("响应IP")
                detection_point = item.get("检测点", "")

                if not ip_address or ip_address == "解析失败":
                    continue

                should_delete = False
                if status == "失败":
                    should_delete = True
                if not should_delete and isinstance(total_time_str, str) and total_time_str.endswith('s'):
                    try:
                        time_val = float(total_time_str[:-1])
                        if time_val >= 8.0:
                            should_delete = True
                    except (ValueError, TypeError):
                        pass

                if should_delete:
                    for cn_name, line_name in carrier_map.items():
                        if detection_point.startswith(cn_name):
                            records_to_delete.append({'ip': ip_address, 'line': line_name})
                            logging.info(
                                f"标记待删除记录: IP={ip_address}, Line={line_name}, 原因: 状态='{status}', 耗时='{total_time_str}'")
                            break

            if records_to_delete:
                unique_records_to_delete = [dict(t) for t in {tuple(d.items()) for d in records_to_delete}]
                logging.info(f"共找到 {len(unique_records_to_delete)} 条唯一的不良记录需要删除。")
                for record in unique_records_to_delete:
                    cf2alidns.delete_record_by_value(
                        domain_name=domain_root,
                        rr=domain_rr,
                        value=record['ip'],
                        line=record['line']
                    )
            else:
                logging.info("最终验证测试结果良好，没有需要删除的DNS记录。")
        except json.JSONDecodeError:
            logging.error("解析第二次测速结果的JSON时出错。")
    else:
        logging.warning("第二次验证测速失败，无法执行剔除操作。")

    logging.info("@@@@@ 本次任务全部执行完毕 @@@@@")
    print("--- over over!!! ---")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [Main] - %(message)s'
    )
    #想法很多，目前只实现了一条路径。fromBc未添加
    main()
