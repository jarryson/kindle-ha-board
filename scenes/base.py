from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageFont

if TYPE_CHECKING:
    from PIL.ImageDraw import ImageDraw


# 🌟 路径配置
class DataPaths:
    """数据与缓存路径管理"""

    DATA_ROOT = Path("data")
    DATA_CONFIG = DATA_ROOT / "config.json"
    DATA_PICTURES = DATA_ROOT / "pictures"

    CACHE_ROOT = Path("cache")
    CACHE_COVERS = CACHE_ROOT / "covers"
    CACHE_PICTURES = CACHE_ROOT / "pictures"

    @classmethod
    def ensure_dirs(cls) -> None:
        """初始化必要目录"""
        for path in [cls.DATA_PICTURES, cls.CACHE_COVERS, cls.CACHE_PICTURES]:
            path.mkdir(parents=True, exist_ok=True)


class BaseBoard:
    """看板基类：提供图像处理、字体加载与文本截断等通用功能"""

    def __init__(
        self,
        global_cfg: dict[str, Any],
        board_cfg: dict[str, Any],
        layout: dict[str, int],
    ):
        self.global_cfg = global_cfg
        self.board_cfg = board_cfg
        self.debug: bool = global_cfg.get("debug", False)
        self.w: int = layout["width"]
        self.h: int = layout["height"]
        self.ram_cache: dict[str, Image.Image] = {}

        # 每个卡片独立的显示设置 (只有配置中存在时才下发，否则保持 None)
        self.wf = board_cfg.get("waveform")
        self.nm = board_cfg.get("nightmode_type")

        DataPaths.ensure_dirs()

    def log(self, tag: str, msg: str, duration: float | None = None) -> None:
        """统一日志输出"""
        if not self.debug:
            return
        dur = f" [{duration:.2f}ms]" if duration is not None else ""
        print(f"[{time.strftime('%H:%M:%S')}] [{tag}]{dur} {msg}")

    def apply_kindle_filter(self, img: Image.Image) -> Image.Image:
        """Atkinson 16级灰度抖动处理"""
        start = time.perf_counter()
        img = img.convert("L")
        width, height = img.size
        # 使用 bytes 直接迭代获取 0-255 整数
        pixels = [float(p) for p in img.tobytes()]

        for y in range(height):
            y_offset = y * width
            for x in range(width):
                idx = y_offset + x
                old_val = pixels[idx]
                new_val = float(max(0, min(255, int(round(old_val / 17.0) * 17))))
                pixels[idx] = new_val

                if (err := (old_val - new_val) / 8.0) == 0:
                    continue

                if x + 1 < width:
                    pixels[idx + 1] += err
                    if x + 2 < width:
                        pixels[idx + 2] += err
                if y + 1 < height:
                    row_next = idx + width
                    if x > 0:
                        pixels[row_next - 1] += err
                    pixels[row_next] += err
                    if x + 1 < width:
                        pixels[row_next + 1] += err
                    if y + 2 < height:
                        pixels[idx + 2 * width] += err

        res = Image.new("L", (width, height))
        res.putdata([int(p) for p in pixels])
        self.log("FILTER", "Atkinson 处理完成", (time.perf_counter() - start) * 1000)
        return res

    def get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """加载配置中的字体，失败则返回默认字体"""
        try:
            return ImageFont.truetype(
                self.global_cfg["font_path"],
                size,
                index=self.global_cfg.get("font_index", 0),
            )
        except Exception as e:
            self.log("FONT", f"加载失败: {e}")
            return ImageFont.load_default()

    def truncate(self, draw: ImageDraw, text: str, font: Any, max_w: int) -> str:
        """精简文本截断"""
        if not text:
            return ""

        for i, char in enumerate(text):
            if char in "(（[【":
                text = text[:i]
                break

        text = " ".join(text.split())

        if not text or draw.textlength(text, font) <= max_w:
            return text

        while text and draw.textlength(f"{text}..", font) > max_w:
            text = text[:-1]

        return f"{text.strip()}.."
