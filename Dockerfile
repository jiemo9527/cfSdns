FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY README.md ./README.md

CMD ["python", "-m", "src.main"]
