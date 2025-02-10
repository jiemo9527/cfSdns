# 使用官方 Python 基础镜像
FROM python:3.11-slim
# 设置时区为上海（东八区）
ENV TZ=Asia/Shanghai

# 确保时区生效
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
# 设置工作目录
WORKDIR /app

# 复制项目文件到容器中
COPY . /app

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 cron 服务
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# 复制 crontab 配置文件
COPY crontab_config /etc/cron.d/cf2alidns_cron

# 设置 crontab 文件的权限
RUN chmod 0644 /etc/cron.d/cf2alidns_cron

# 应用 crontab 配置
RUN crontab /etc/cron.d/cf2alidns_cron

# 启动 cron 服务
CMD ["cron", "-f"]
