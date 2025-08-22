# -*- coding: utf-8 -*-
import asyncio
import getIPFromW3
import webTestUnion
import cf2alidns
import logging
import json


def filter_cesu_results(json_output: str) -> list:
    """
    根据指定条件筛选CESU.AI的测试结果。

    剔除规则 (任一条件满足即剔除整条记录):
    1. 任意节点的“状态”为“访问失败”。
    2. 任意节点的“耗时”大于 3.0 秒。
    3. 任意节点的“耗时”不是一个有效的数值 (例如 '--')。

    :param json_output: run_cesu_test函数返回的原始JSON字符串。
    :return: 一个经过筛选、只包含合格项目的新列表。如果输入无效则返回空列表。
    """
    try:
        # 将JSON字符串解析为Python列表
        results_list = json.loads(json_output)
        if not isinstance(results_list, list):
            print("错误：输入的JSON不是一个列表结构。")
            return []
    except (json.JSONDecodeError, TypeError):
        print("错误：无法解析输入的JSON字符串。")
        return []

    # 用于存放合格结果的新列表
    filtered_list = []

    # 定义结果中不属于检测节点的键
    non_node_keys = {"序号", "检测目标", "异常节点(占比)", "操作"}

    # 遍历原始列表中的每一条结果（每一个序号）
    for item in results_list:
        is_valid = True  # 先假定当前条目是合格的

        # 遍历当前条目中的每一个键值对，检查所有检测节点
        for key, node_data in item.items():
            # 跳过非节点数据
            if key in non_node_keys or not isinstance(node_data, dict):
                continue

            # --- 开始检查节点的三个剔除条件 ---
            status = node_data.get("状态")
            time_str = node_data.get("耗时")

            # 条件1: 状态为“访问失败”
            if status == "访问失败":
                print(f"剔除 [序号: {item.get('序号', 'N/A')}]，原因：节点 {key} 状态为“访问失败”。")
                is_valid = False
                break  # 已不合格，无需再检查此条目的其他节点

            # 条件2 & 3: 检查耗时
            if isinstance(time_str, str) and time_str.endswith('s'):
                try:
                    # 尝试移除 's' 并转换为浮点数
                    time_value = float(time_str[:-1])
                    if time_value > 3.0:
                        print(f"剔除 [序号: {item.get('序号', 'N/A')}]，原因：节点 {key} 耗时 {time_str} > 3.0s。")
                        is_valid = False
                        break  # 已不合格
                except ValueError:
                    # 如果转换失败，说明耗时不是数值
                    print(f"剔除 [序号: {item.get('序号', 'N/A')}]，原因：节点 {key} 耗时 '{time_str}' 非数值。")
                    is_valid = False
                    break  # 已不合格
            else:
                # 如果耗时格式不正确或不是字符串，也视为不合格
                print(f"剔除 [序号: {item.get('序号', 'N/A')}]，原因：节点 {key} 耗时 '{time_str}' 格式无效或非数值。")
                is_valid = False
                break  # 已不合格

        # 如果遍历完所有节点后，is_valid 仍然为 True，则将其加入新列表
        if is_valid:
            filtered_list.append(item)

    return filtered_list


def main():
    """
    主函数，用于执行从获取Cloudflare IP到更新阿里云DNS的完整流程。
    """
    logging.info("--- 开始执行主流程 ---")

    # 步骤1：获取
    logging.info("正在执行IP获取...")
    ct_ip, cm_ip, cu_ip = getIPFromW3.get_cf_ips()
    logging.info("IP获取完成。")


    ###步骤2：清洗

    json_dx = asyncio.run(webTestUnion.run_cesu_test(target_urls=ct_ip, cookies=cesuck))
    print(json_dx)
    if json_dx:
        # 2. 调用筛选函数处理原始结果
        #    这一步会返回一个只包含合格项目的列表，每个项目都是一个字典
        filtered_list = filter_cesu_results(json_dx)
        # 3. 从筛选后的列表中提取IP地址
        if filtered_list:
            # 使用列表推导式，从每个合格的字典中提取 "检测目标" 的值
            qualified_ips = [item['检测目标'] for item in filtered_list]
            print(f"共找到 {len(qualified_ips)} 个合格的IP。")
            print(qualified_ips)
        else:
            print("\n--- 筛选后无任何合格IP ---")
    else:
        print("\n[CESU.AI] 未能获取到JSON结果。")



    # 步骤3：更新&再次剔除
    logging.info("正在执行阿里云DNS更新...")
    cf2alidns.update_aliyun_dns_records(cm_ip=cm_ip, cu_ip=cu_ip, ct_ip=ct_ip)
    logging.info("阿里云DNS更新完成。")

    logging.info("--- 主流程成功执行完毕 ---")


if __name__ == '__main__':
    # 为主流程执行配置基础日志。
    # 注意：cf2alidns.py为其DNS相关操作配置了自己的日志文件。
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [Main] - %(message)s'
    )
    main()
