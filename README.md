# 关于
重新构建了一套，集互联网优选服务器之大成者，适用于优化网站的访问。

为什么从 **dnspod（腾讯）** 转到 **阿里云 DNS**？  
主要还是考虑每条线路限制数的问题。

| 服务商    | 免费套餐 | 最低阶付费 | 收费金额                   |
|-----------|----------|------------|----------------------------|
| **dnspod** | 2条      | 10条       | 99元/年起                  |
| **alidns** | 10条     | 100条      | 58元/年起（优惠后可28元）  |

### 特色：
- 通过100条的线路数将每个运营商线路拉满，100条占满后，新增记录时会自动剔除最老的记录。性价比拉满
- 由于每域A和cname类型不能共用一个线路，所收集的泛播地址暂未使用。后续想办法处理

---

# 使用
1.  `pip install aliyun-python-sdk-core aliyun-python-sdk-alidns cloudscraper`
2.  填写alidns-key
3.  每5分钟`python cf2alidns.py`（不得低于2分钟/次）

### 上效果图（刚刚跑满，还没到最佳）
![Snipaste_2025-02-08_19-50-34.jpg](Snipaste_2025-02-08_19-50-34.jpg)
### 感谢
<https://github.com/ddgth/cf2dns>


<https://github.com/ZhiXuanWang/cf-speed-dns>