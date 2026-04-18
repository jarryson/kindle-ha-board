from __future__ import annotations

import time
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from PIL import Image, ImageDraw

from .base import BaseBoard, DataPaths


class MusicBoard(BaseBoard):
    """音乐播放器看板：处理封面图抓取、元数据渲染及增量更新指令"""

    def __init__(
        self,
        global_cfg: dict[str, Any],
        board_cfg: dict[str, Any],
        layout: dict[str, int],
    ):
        super().__init__(global_cfg, board_cfg, layout)
        self.cover_dir = DataPaths.CACHE_COVERS

        # 状态追踪：用于增量更新判断
        self.last_url: str | None = None
        self.last_title: str | None = None
        self.last_artist: str | None = None
        self.last_img_v: int = 0

    def _get_cover(self, url: str) -> Image.Image | None:
        """获取并处理专辑封面图"""
        if not url:
            return None

        # 提取缓存 ID
        parsed = urlparse(url)
        cid = parse_qs(parsed.query).get("cache", ["default"])[0]
        cpath = self.cover_dir / cid[:2] / f"{cid}.png"

        if cid in self.ram_cache:
            return self.ram_cache[cid]

        if cpath.exists():
            img = Image.open(cpath).convert("L")
            self._update_cache(cid, img)
            return img

        start = time.perf_counter()
        try:
            ha_host = self.global_cfg.get("ha_host", "")
            full_url = f"http://{ha_host}{url}" if url.startswith("/") else url
            res = requests.get(full_url, timeout=5)
            if res.ok:
                with Image.open(BytesIO(res.content)) as raw:
                    img = raw.resize((self.w, self.w), Image.Resampling.LANCZOS)
                    processed = self.apply_kindle_filter(img)
                    self._update_cache(cid, processed)
                    cpath.parent.mkdir(parents=True, exist_ok=True)
                    processed.save(cpath)
                    self.log(
                        "DOWNLOAD",
                        f"封面成功: {cid}",
                        (time.perf_counter() - start) * 1000,
                    )
                    return processed
        except Exception as e:
            self.log("ERR", f"封面获取失败: {e}")
        return None

    def _apply_opts(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """为指令注入面板独立的波形和夜间模式配置 (仅在存在时)"""
        if self.wf is not None:
            cmd["waveform"] = self.wf
        if self.nm is not None:
            cmd["nightmode"] = self.nm
        return cmd

    def render(self, attr: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
        """执行主渲染流程"""
        start = time.perf_counter()
        canvas = Image.new("L", (self.w, self.h), 255)
        draw = ImageDraw.Draw(canvas)

        url = attr.get("entity_picture", "")
        title = attr.get("media_title", "Unknown Title")
        artist = attr.get("media_artist", "Unknown Artist")

        t_size, a_size = self.w // 9, self.w // 13
        f_t, f_a = self.get_font(t_size), self.get_font(a_size)

        s_t = self.truncate(draw, title, f_t, self.w - 60)
        s_a = self.truncate(draw, artist, f_a, self.w - 60)

        if cover := self._get_cover(url):
            canvas.paste(cover, (0, 0))

        draw.text((self.w // 2, self.w + 20), s_t, font=f_t, fill=0, anchor="mt")
        draw.text((self.w // 2, self.w + 110), s_a, font=f_a, fill=100, anchor="mt")

        # 3. 增量指令构建
        cmds = []
        if url != self.last_url:
            self.last_url = url
            self.last_img_v = int(time.time())

        if s_t != self.last_title:
            self.last_title = s_t
            cmds.append(
                {
                    "type": "TXT",
                    "text": f"**{s_t}**",
                    "top": self.w + 20,
                    "px": t_size,
                    "use_format": True,
                    "padding": "HORIZONTAL",
                    "center": True,
                    "refresh": False,
                }
            )

        if s_a != self.last_artist:
            self.last_artist = s_a
            cmds.append(
                {
                    "type": "TXT",
                    "text": s_a,
                    "top": self.w + 110,
                    "px": a_size,
                    "padding": "HORIZONTAL",
                    "center": True,
                    "refresh": False,
                }
            )

        # 4. 只有最后的 REFRESH 指令携带波形参数
        if cmds:
            cmds.append(self._apply_opts({"type": "REFRESH"}))
            for idx, c in enumerate(cmds):
                c["seq"] = idx

        self.log(
            "RENDER", f"MusicBoard 完成: {s_t}", (time.perf_counter() - start) * 1000
        )

        return canvas, {
            "v": int(time.time()),
            "img_v": self.last_img_v,
            "count": len(cmds),
            "commands": cmds,
        }
