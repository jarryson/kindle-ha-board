Kindle-HABoard

Kindle-HABoard 是一个用gemini协助编写的将 Kindle HA 音乐看板的服务端程序，平时展示其他面板（目前只有图片功能）。

它能够实时抓取 Home Assistant (HA) 中的媒体播放器状态，并将专辑封面、歌曲信息以优化的 16 级灰度图像和矢量文字形式推送到 Kindle 屏幕上。

<img width="600" height="800" alt="image" src="https://github.com/user-attachments/assets/602d8487-ab97-4f78-b72a-5d5358eeea47" />

🌟 核心特性
兼容模式：会实时渲染完整播放图，兼容如online screensaver之类越狱插件。

高性能渲染: 服务端采用 Python Pillow 处理图像，支持 16 级 Floyd-Steinberg 灰度抖动，适配 E-Ink 屏幕特性。

增量更新: 定制脚本用fbink命令，采用“先批量写入显存，后统一刷新物理屏”的策略，降低 Kindle 功耗，同时减少屏幕刷新次数。支持歌曲名/艺术家单独刷新。

双模式切换: 播放音乐时显示播放器信息，闲置时自动进入本地图片轮播模式（/app/data/picture）。

多设备支持：理论支持多部kindle（未测试完成）。

Docker 化部署: 支持 GitHub Container Registry (GHCR)，适配 AMD64 和 ARM64 (CoreELEC/树莓派) 架构。

🚀 快速开始 (服务端)

1. 准备配置文件

在宿主机创建 data 目录，放入你的字体font.ttf，并新建 config.json：
（kindle8为你定义的kindle名称）

{
    "ha_host": "你的HA_IP:8123",
    "ha_token": "你的长期访问令牌",
    "server_port": 8135,
    "debug": true,
    "font_path": "/app/data/font.ttf",
    "devices": {
        "kindle8": {
            "entity_id": "media_player.your_player",
            "timeout": 600,
            "waveform": "AUTO",
            "layout": {"width": 600, "height": 800},
            "board": { "type": "picture", "interval": 1800 }
        }
    }
}


2. 使用 Docker Compose 部署

创建 docker-compose.yml:

services:
  kindle-haboard:
    image: ghcr.io/jarryson/kindle-ha-board:latest
    container_name: kindle-haboard
    restart: unless-stopped
    ports:
      - "8135:8135"
    volumes:
      - ./data:/app/data
      - kindle_board_cache:/app/cache

volumes:
  kindle_board_cache:


运行服务：docker compose up -d


🛠️ 常见问题

Q: 屏幕全白，没有文字？

A: 请检查 config.json 中的 font_path 是否正确指向了容器内存在的 .ttf 文件。

Q: 无法连接 Home Assistant？

A: 不要使用 localhost，请使用 HA 的局域网物理 IP。如果是 Docker 运行，请检查防火墙。

📄 开源协议

MIT License
