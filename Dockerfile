# --- 第一阶段：构建环境 (Builder) ---
FROM python:3.11-slim AS builder

# 安装编译 Pillow 所需的开发头文件和编译器
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
COPY requirements.txt .

# 将依赖安装到用户目录下，方便后续拷贝
RUN pip install --user --no-cache-dir -r requirements.txt

# --- 第二阶段：运行环境 (Runner) ---
FROM python:3.11-slim

WORKDIR /app

# 1. 仅安装运行所需的动态库 (不安装编译器)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# 2. 从第一阶段拷贝安装好的 Python 包
COPY --from=builder /root/.local /root/.local

# 3. 拷贝项目代码
COPY . .

# 4. 配置环境变量，确保能找到拷贝过来的库
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8135

CMD ["python", "main.py"]