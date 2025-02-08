# 关于
重新构建了一套，集互联网优选服务器之大成者，适用于优化网站的访问。

为什么从 **dnspod（腾讯）** 转到 **阿里云 DNS**？  
主要还是考虑每条线路限制数的问题。

| 服务商    | 免费套餐 | 最低阶付费 | 收费金额                   |
|-----------|----------|------------|----------------------------|
| **dnspod** | 2条      | 10条       | 99元/年起                  |
| **alidns** | 10条     | 100条      | 58元/年起（优惠后可28元）  |

### 特色：
- 通过100条的线路数将每个运营商拉满，100条占满后，新增记录时会自动删除最老的记录。

---

# 使用
1.  `pip install aliyun-python-sdk-core aliyun-python-sdk-alidns cloudscraper`
2.  填写alidns-key
3.  每5分钟`python cf2alidns.py`（不得低于2分钟/次）

# 感谢
<https://github.com/ddgth/cf2dns>


<https://github.com/ZhiXuanWang/cf-speed-dns>