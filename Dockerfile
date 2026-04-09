# tdxview Docker镜像
# 基于Python 3.9 slim镜像

FROM python:3.9-slim AS builder

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /app

# 切换到非root用户
USER appuser

# 创建必要的目录
RUN mkdir -p /app/data /app/logs /app/plugins

# 设置数据目录权限
RUN chmod 755 /app/data /app/logs /app/plugins

# 暴露端口
EXPOSE 8501

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/health || exit 1

# 启动命令
CMD ["streamlit", "run", "app/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false", \
    "--browser.serverAddress=0.0.0.0", \
    "--browser.gatherUsageStats=false"]

# 多阶段构建 - 生产镜像
FROM python:3.9-slim AS production

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从builder阶段复制已安装的包
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY --from=builder /app /app

# 创建非root用户
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# 创建必要的目录
RUN mkdir -p /app/data /app/logs /app/plugins

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    LOG_DIR=/app/logs \
    PLUGIN_DIR=/app/plugins \
    CONFIG_FILE=/app/config.yaml \
    ENVIRONMENT=production

# 暴露端口
EXPOSE 8501

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/health || exit 1

# 启动命令
CMD ["streamlit", "run", "app/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false", \
    "--browser.serverAddress=0.0.0.0", \
    "--browser.gatherUsageStats=false"]

# 开发镜像标签
FROM builder AS development

# 安装开发工具
USER root
RUN apt-get update && apt-get install -y \
    vim \
    less \
    && rm -rf /var/lib/apt/lists/*

USER appuser

# 设置开发环境变量
ENV ENVIRONMENT=development \
    DEBUG=true

# 开发环境启动命令（支持热重载）
CMD ["streamlit", "run", "app/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=false", \
    "--server.runOnSave=true", \
    "--server.enableCORS=true", \
    "--browser.serverAddress=0.0.0.0", \
    "--browser.gatherUsageStats=false"]