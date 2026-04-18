from __future__ import annotations

import time
import zlib
from typing import Any

from PIL import Image

from .base import BaseBoard, DataPaths


class PictureBoard(BaseBoard):
    """图片轮播看板：自动扫描目录并定期更新图片"""

    def __init__(
        self,
        global_cfg: dict[str, Any],
        board_cfg: dict[str, Any],
        layout: dict[str, int],
    ):
        super().__init__(global_cfg, board_cfg, layout)
        self.src_dir = DataPaths.DATA_PICTURES
        self.cache_dir = DataPaths.CACHE_PICTURES

        self.interval: int = board_cfg.get("interval", 1800)
        self.last_switch: float = 0
        self.last_img_v: int = 0
        self.index: int = 0
        self.playlist: list[dict[str, str]] = []

        self._scan()

    def _scan(self) -> None:
        """扫描源目录中的图片并生成播放列表"""
        start = time.perf_counter()
        valid_exts = {".jpg", ".png", ".jpeg", ".webp"}
        files = sorted(
            [f for f in self.src_dir.glob("*") if f.suffix.lower() in valid_exts]
        )

        self.playlist = []
        for f in files:
            crc = 0
            with open(f, "rb") as rb:
                while chunk := rb.read(65536):
                    crc = zlib.crc32(chunk, crc)
            self.playlist.append({"path": str(f), "hash": f"{crc & 0xFFFFFFFF:08x}"})

        self.log(
            "SCAN",
            f"同步播放列表 ({len(self.playlist)}张)",
            (time.perf_counter() - start) * 1000,
        )

    def _get_image(self, item: dict[str, str]) -> Image.Image:
        """获取并处理图片"""
        cpath = self.cache_dir / f"{item['hash']}.png"
        if cpath.exists():
            return Image.open(cpath).convert("L")

        start = time.perf_counter()
        with Image.open(item["path"]) as img:
            ir, tr = img.width / img.height, self.w / self.h
            if ir > tr:
                nw = int(tr * img.height)
                left = (img.width - nw) // 2
                img = img.crop((left, 0, left + nw, img.height))
            else:
                nh = int(img.width / tr)
                top = (img.height - nh) // 2
                img = img.crop((0, top, img.width, top + nh))

            img = img.resize((self.w, self.h), Image.Resampling.LANCZOS)
            processed = self.apply_kindle_filter(img)
            processed.save(cpath)
            self.log(
                "FILTER",
                f"处理新图片: {item['hash']}",
                (time.perf_counter() - start) * 1000,
            )
            return processed

    def render(
        self, ha_cache: Any = None
    ) -> tuple[Image.Image | None, dict[str, Any] | None]:
        """主渲染逻辑"""
        now = time.time()
        if not self.playlist:
            return None, None

        if self.last_switch != 0 and (now - self.last_switch <= self.interval):
            return None, None

        if self.last_switch != 0:
            self.index = (self.index + 1) % len(self.playlist)

        self.last_switch = now
        self.last_img_v = int(now)
        item = self.playlist[self.index]
        canvas = self._get_image(item)

        cmd: dict[str, Any] = {"type": "IMG", "flash": True, "refresh": True, "seq": 0}
        if self.wf is not None:
            cmd["waveform"] = self.wf
        if self.nm is not None:
            cmd["nightmode"] = self.nm

        return canvas, {
            "v": self.last_img_v,
            "img_v": self.last_img_v,
            "count": 1,
            "commands": [cmd],
        }
