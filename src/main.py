# -*- coding: utf-8 -*-
import getIPFromW3
import cf2alidns
import logging


def main():
    """
    主函数，用于执行从获取Cloudflare IP到更新阿里云DNS的完整流程。
    """
    logging.info("--- 开始执行主流程 ---")

    # 步骤1：获取、筛选并测试Cloudflare IP，以获得最佳节点。
    # givemeCFIP模块中的get_cf_ips函数负责处理这整个子流程。
    logging.info("正在执行IP获取...")
    ct_ip, cm_ip, cu_ip = getIPFromW3.get_cf_ips()
    logging.info("IP获取完成。")

    # 步骤2：使用新获取的IP更新阿里云DNS记录。
    # cf2alidns模块中的update_aliyun_dns_records函数负责处理此操作。
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
