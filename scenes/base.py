from __future__ import annotations

import array
import gc
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
    """看板基类：针对低内存环境优化"""

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

        # 内存优化：限制缓存数量，防止无限增长
        self.ram_cache: dict[str, Image.Image] = {}
        self.max_cache_size = 5

        self.wf = board_cfg.get("waveform")
        self.nm = board_cfg.get("nightmode_type")

        DataPaths.ensure_dirs()

    def _update_cache(self, key: str, img: Image.Image):
        """带容量限制的缓存更新"""
        if len(self.ram_cache) >= self.max_cache_size:
            # 弹出最早进入的项
            self.ram_cache.pop(next(iter(self.ram_cache)))
        self.ram_cache[key] = img

    def log(self, tag: str, msg: str, duration: float | None = None) -> None:
        if not self.debug:
            return
        dur = f" [{duration:.2f}ms]" if duration is not None else ""
        print(f"[{time.strftime('%H:%M:%S')}] [{tag}]{dur} {msg}")

    def apply_kindle_filter(self, img: Image.Image) -> Image.Image:
        """Atkinson 抖动处理 (内存优化版)"""
        start = time.perf_counter()
        img = img.convert("L")
        width, height = img.size

        # 🌟 核心优化：使用 array.array 替代 list，节省约 80% 的临时内存占用
        # 'f' 代表 float32 (4 bytes per element)
        pixels = array.array("f", img.tobytes())

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

        # 将处理后的数据转回图像并释放 array 内存
        res = Image.new("L", (width, height))
        res.putdata([int(p) for p in pixels])

        del pixels  # 显式释放数组
        self.log("FILTER", "Atkinson 处理完成", (time.perf_counter() - start) * 1000)
        return res

    def get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
