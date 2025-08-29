# 使用playwright官方镜像
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# --- 修正时区设置 ---
# 设置环境变量，避免在安装tzdata时出现交互式提示
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 更新软件包列表，安装tzdata，然后设置时区
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    # 清理apt缓存，减小镜像体积
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# --- 优化依赖安装步骤 ---
# 先只复制依赖文件，这样当代码改变而依赖不变时，可以利用缓存
COPY requirements.txt .

# 升级pip并安装依赖
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目中的所有文件到工作目录
COPY . .

# 设置容器启动时要执行的默认命令
CMD ["python", "main.py"]
