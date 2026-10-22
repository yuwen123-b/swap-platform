# Hugging Face Spaces（Docker 模式）部署文件
# HF 强制容器监听 7860 端口；数据库等敏感配置一律走 Spaces 的 Variables/Secrets
# （环境变量优先级高于 .env 文件，容器内不含 .env 也能正常启动）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先只拷依赖清单再安装：利用 Docker 层缓存，代码变更不触发重装依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# app/ 是代码；sql/ 必须一起拷贝——initialize_schema 每次启动都会读取
# 项目根目录 sql/*.sql 建表与做幂等迁移（app/db/pool.py 的 SQL_DIR 指向 parents[2]/sql）
COPY app ./app
COPY sql ./sql

# uploads/ 在容器内可写；HF 容器重启即清空（云端文件属临时存储，正式持久化需接对象存储）
# 顺手在构建期创建，避免只读文件系统上报错；业务内层目录（items/tts/...）启动与写文件时自动补建
RUN mkdir -p /app/uploads

# HF Spaces 以非 root（UID 1000）运行容器，提前赋权保证 uploads 可写
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

# Hugging Face 强制要求暴露 7860
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
