# --- Stage 1: Build environment (Builder) ---
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# 安装完整的开发头文件，确保 Pillow 编译时开启所有功能支持
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

# 编译并安装依赖到用户目录
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime environment (Runner) ---
FROM python:3.11-slim

WORKDIR /app

# 安装运行时动态库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    liblcms2-2 \
    libwebp7 \
    libtiff6 \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段拷贝已安装的 Python 包
COPY --from=builder /root/.local /root/.local

# 配置环境变量
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/root/.local/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1

# 🌟 核心改进：构建时自检 (Sanity Check)
# 如果 Pillow 加载失败或缺失 _imaging 模块，RUN 指令将返回非零状态码，导致打包终止
RUN python3 -c "from PIL import Image, _imaging; print('Pillow 模块验证通过: _imaging 加载正常')"

# 拷贝项目代码
COPY . .

# 确保必要的目录存在
RUN mkdir -p data/pictures cache

EXPOSE 8135

CMD ["python", "main.py"]