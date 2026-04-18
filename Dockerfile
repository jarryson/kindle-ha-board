# --- Stage 1: Build environment (Builder) ---
FROM python:3.11-slim AS builder

# 安装编译所需的开发头文件
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libtiff-dev \
    libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
COPY requirements.txt .

# 安装依赖
RUN pip install --user --no-cache-dir -r requirements.txt


# --- Stage 2: Runtime environment (Runner) ---
FROM python:3.11-slim

WORKDIR /app

# 安装运行时动态库，确保 Pillow 渲染正常
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    liblcms2-2 \
    libwebp7 \
    libtiff6 \
    libopenjp2-7 \
    libharfbuzz0b \
    libfribidi0 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段拷贝已安装的 Python 包
COPY --from=builder /root/.local /root/.local

# 配置环境变量
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/root/.local/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1

# 验证关键依赖是否安装成功
RUN python3 -c "from PIL import Image, _imaging; print('Pillow 模块验证通过')"
RUN python3 -c "import aiohttp; print('aiohttp 模块验证通过')"

# 拷贝项目代码
COPY . .

# 创建必要目录
RUN mkdir -p data/pictures cache/covers cache/pictures

# 默认端口 (需与 config.json 保持一致)
EXPOSE 8135

# 启动 (aiohttp 纯异步驱动)
CMD ["python", "main.py"]
