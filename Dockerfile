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

RUN pip install --no-cache-dir -r requirements.txt

# 步骤 5: 安装 Playwright 所需的浏览器核心
RUN playwright install chromium

# 步骤 6: 复制项目中的所有文件到工作目录
COPY . .

# 步骤 7: 设置容器启动时要执行的默认命令
# 当容器运行时，会自动执行 python main.py
CMD ["python", "main.py"]
