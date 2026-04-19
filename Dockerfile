# --- Stage 1: Builder ---
FROM python:3.11-alpine AS builder

# 安装编译所需的 build-base 和相关开发库 (Alpine 环境)
RUN apk add --no-cache \
    build-base \
    jpeg-dev \
    zlib-dev \
    freetype-dev \
    lcms2-dev \
    openjpeg-dev \
    tiff-dev \
    libwebp-dev \
    harfbuzz-dev \
    fribidi-dev

WORKDIR /install
COPY requirements.txt .

# 安装依赖并排除文档等冗余内容
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Runner ---
FROM python:3.11-alpine

# 从构建参数接收版本号
ARG VERSION=1.4.2

LABEL org.opencontainers.image.title="Kindle-HABoard" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.description="Kindle Home Assistant Dashboard for E-ink optimization"

WORKDIR /app

# 仅安装运行时所需的动态库
RUN apk add --no-cache \
    libjpeg-turbo \
    libpng \
    freetype \
    lcms2 \
    openjpeg \
    libwebp \
    harfbuzz \
    fribidi

# 从 builder 阶段拷贝 python 环境
COPY --from=builder /root/.local /root/.local

# 配置环境变量
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=$VERSION

# 拷贝代码
COPY . .

# 验证
RUN python3 -c "from PIL import Image; print('Pillow 模块验证通过')"

# 目录预设 (持久化挂载点)
RUN mkdir -p data/pictures cache/covers cache/pictures

EXPOSE 8135

CMD ["python", "main.py"]
