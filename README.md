# 引入了奇奇怪怪的数据源，加入了缓存域和自动删除记录功能。最低要求2.5核2.5G

### docker-compose运行
```
services:
  cfsdns:
    image: wanxve0000/cfsdns:latest
    restart: unless-stopped
    shm_size: '2g'
    environment:
      ALIYUN_ACCESS_KEY_ID: "ALIYUN_ACCESS_KEY_ID"
      ALIYUN_ACCESS_KEY_SECRET: "ALIYUN_ACCESS_KEY_SECRET"
      ALIYUN_PACKAGE_NUM: "100"
      SLEEPTIME: "1800"
      domain_rr: "www"
      domain_root: "domain.com"
      HEALTHCHECK_URL: "https://www.domain.com/health"
      HEALTHCHECK_TIMEOUT_SECONDS: "10"
      HEALTHCHECK_EXPECT_STATUS: "200"
```

说明：Docker 镜像默认入口已统一为 `python -m src.main`。
iStoreOS 常见的 `x86_64` 对应 Docker 平台 `linux/amd64`；当前镜像同时支持 `linux/amd64` 和 `linux/arm64`。
当前推荐运行参数：`temp=20`、`floor=3`、`target=6`、`ceiling=8`，二测异常阈值为 `2.0s`。
`domain_rr` 会保守维护生产池，并对超出 `ceiling` 的旧记录做逐轮温和收敛，不会一次性大规模清空。

### python运行
```
cat << EOF > .env
# 阿里云 DNS 配置
ALIYUN_ACCESS_KEY_ID="请在这里填入您的Access Key ID"
ALIYUN_ACCESS_KEY_SECRET="请在这里填入您的Access Key Secret"
ALIYUN_PACKAGE_NUM="100" # alidns 套餐线路数上限
SLEEPTIME="1800" # 任务休眠时间，推荐 30 分钟

# 生效域名配置
domain_rr="www"
domain_root="domain.com"
HEALTHCHECK_URL="https://www.domain.com/health"
HEALTHCHECK_TIMEOUT_SECONDS="10"
HEALTHCHECK_EXPECT_STATUS="200"
EOF

pip install -r requirements.txt
playwright install-deps
playwright install chromium
python -m src.main
```

说明：本地标准启动方式统一为在仓库根目录执行 `python -m src.main`。
根目录 `.env` 是标准配置位置；代码仍兼容历史 `src/.env`，但根目录配置优先级更高。

### docker-cli运行
```
docker run --rm \
  -d \
  --name cfsdns\
  --restart unless-stopped \
  --shm-size=2g \
  -e ALIYUN_ACCESS_KEY_ID="请替换为您的AccessKeyID" \
  -e ALIYUN_ACCESS_KEY_SECRET="请替换为您的AccessKeySecret" \
  -e ALIYUN_PACKAGE_NUM="100" \
  -e domain_rr="www" \
  -e SLEEPTIME="1800" \
  -e domain_root="domain.com" \
  -e HEALTHCHECK_URL="https://www.domain.com/health" \
  -e HEALTHCHECK_TIMEOUT_SECONDS="10" \
  -e HEALTHCHECK_EXPECT_STATUS="200" \
  wanxve0000/cfsdns:latest
```

为什么从 **dnspod（腾讯）** 转到 **阿里云 DNS**？  
主要还是考虑每条线路限制数的问题。

| 服务商    | 免费套餐 | 最低阶付费 | 收费金额                   |
|-----------|----------|------------|----------------------------|
| **dnspod** | 2条      | 10条       | 99元/年起                  |
| **alidns** | 10条     | 100条      | 58元/年起（优惠后可28元）  |



### 特点：
#### 基于多源数据的 IP 优选

- 通过访问多个在线资源，实时提取和更新最优 IP 地址，确保网络路径的最小延迟和最大吞吐量。
- 针对不同运营商（如移动、联通、电信）的 IP 地址进行精细化分类，优化用户的访问路径。

#### 基于阿里云 API 的自动化 DNS 管理

- 利用阿里云的 API 接口，实现 DNS 记录的全生命周期管理，包括查询、添加、更新和删除。
- 内置去重和冲突检测机制，确保 DNS 记录的唯一性和准确性。

#### 基于动态调整的资源优化

- `temp` 作为内部测速池，会按本轮候选精确同步，不会无限累积历史记录。
- `domain_rr` 作为对外生产解析，会按 `floor/target/ceiling` 保守维护，并对超出上限的旧记录做逐轮温和收敛。
- 第二轮测速中，`状态=失败`、`总耗时>=2.0s`、以及 `解析失败` 等异常信号都会参与异常判断与冻结逻辑。
- 通过动态调整机制，持续优化网络性能，同时避免因单轮波动造成大规模误删。


---




### latest分支运行12小时后效果图
![Snipaste_01.png](Snipaste_01.png)
![Snipaste_02.png](Snipaste_02.png)
### 感谢
<https://github.com/ddgth/cf2dns>

<https://github.com/ZhiXuanWang/cf-speed-dns>
