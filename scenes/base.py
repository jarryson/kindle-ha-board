from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageFont

if TYPE_CHECKING:
    from PIL.ImageDraw import ImageDraw


class DataPaths:
    DATA_ROOT = Path("data")
    DATA_CONFIG = DATA_ROOT / "config.json"
    DATA_PICTURES = DATA_ROOT / "pictures"
    CACHE_ROOT = Path("cache")
    CACHE_COVERS = CACHE_ROOT / "covers"
    CACHE_PICTURES = CACHE_ROOT / "pictures"

    @classmethod
    def ensure_dirs(cls) -> None:
        for path in [cls.DATA_PICTURES, cls.CACHE_COVERS, cls.CACHE_PICTURES]:
            path.mkdir(parents=True, exist_ok=True)


class BaseBoard:
    requires_ha = False

    def __init__(
        self,
        global_cfg: dict[str, Any],
        board_cfg: dict[str, Any],
        layout: dict[str, int],
    ):
        self.global_cfg = global_cfg
        self.board_cfg = board_cfg
        self.debug: bool = global_cfg.get("debug", False)
        self.w, self.h = layout["width"], layout["height"]
        self.ram_cache: dict[str, Image.Image] = {}
        self.max_cache_size = 5
        self.wf = board_cfg.get("waveform")
        self.nm = board_cfg.get("nightmode_type")
        DataPaths.ensure_dirs()

    def _update_cache(self, key: str, img: Image.Image):
        if len(self.ram_cache) >= self.max_cache_size:
            self.ram_cache.pop(next(iter(self.ram_cache)))
        self.ram_cache[key] = img

    def log(self, tag: str, msg: str, duration: float | None = None) -> None:
        if not self.debug:
            return
        dur = f" [{duration:.2f}ms]" if duration is not None else ""
        print(f"[{time.strftime('%H:%M:%S')}] [{tag}]{dur} {msg}")

    def apply_kindle_filter(
        self, img: Image.Image, target_size: tuple[int, int] | None = None
    ) -> Image.Image:
        """
        Kindle 图像综合处理：
        1. 转换为灰度 (先转换，减少后续缩放计算量)
        2. 缩放至目标尺寸
        3. Atkinson 抖动处理
        """
        start = time.perf_counter()

        # 🌟 1. 先转灰度，变 3 通道为 1 通道
        img = img.convert("L")

        # 🌟 2. 缩放 (如果提供了目标尺寸)
        size = target_size or (self.w, self.h)
        if img.size != size:
            # 使用 BILINEAR 兼顾速度与质量，L 模式下效果已足够
            img = img.resize(size, Image.Resampling.BILINEAR)

        w, h = img.size
        pw, ph = w + 2, h + 2
        pix = [0] * (pw * ph)

        # 将灰度数据填入带 Padding 的缓冲区
        raw = img.tobytes()
        for y in range(h):
            pix[y * pw : y * pw + w] = list(raw[y * w : y * w + w])

        lut = [0] * 1024
        for i in range(1024):
            val = i - 256
            lut[i] = max(0, min(255, (val + 8) // 17 * 17))

        _pix, _lut = pix, lut
        OFF_1_0, OFF_2_0 = 1, 2
        OFF_M1_1, OFF_0_1, OFF_1_1 = pw - 1, pw, pw + 1
        OFF_0_2 = pw * 2

        for y in range(h):
            idx = y * pw
            for _ in range(w):
                old_val = _pix[idx]
                new_val = _lut[old_val + 256]
                _pix[idx] = new_val
                if err := (old_val - new_val) >> 3:
                    _pix[idx + OFF_1_0] += err
                    _pix[idx + OFF_2_0] += err
                    _pix[idx + OFF_M1_1] += err
                    _pix[idx + OFF_0_1] += err
                    _pix[idx + OFF_1_1] += err
                    _pix[idx + OFF_0_2] += err
                idx += 1

        res_pix = [0] * (w * h)
        for y in range(h):
            res_pix[y * w : (y + 1) * w] = _pix[y * pw : y * pw + w]

        res = Image.new("L", (w, h))
        res.putdata(res_pix)
        self.log("FILTER", f"处理完成 ({w}x{h})", (time.perf_counter() - start) * 1000)
        return res

    def render(self, attr: Any = None) -> tuple[Any, Any]:
        raise NotImplementedError

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
