import requests, time, threading
from io import BytesIO
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw
from .base import BaseBoard, DataPaths

class MusicBoard(BaseBoard):
    def __init__(self, config, layout, d_cfg):
        super().__init__(config, layout)
        self.cover_dir = DataPaths.CACHE_COVERS
        
        # 状态追踪：用于判断是否需要下发指令
        self.last_url = None
        self.last_title = None
        self.last_artist = None
        
        self.last_img_v = 0
        # 从配置获取参数，如果没有配置则为 None
        self.wf = d_cfg.get("waveform")
        self.nm = d_cfg.get("nightmode_type")

    def _get_cover(self, url):
        if not url: return None
        parsed = urlparse(url)
        cid = parse_qs(parsed.query).get('cache', ['default'])[0]
        cpath = self.cover_dir / cid[:2] / f"{cid}.png"
        
        if cid in self.ram_cache: return self.ram_cache[cid]
        if cpath.exists():
            img = Image.open(cpath).convert('L')
            self.ram_cache[cid] = img
            return img

        start = time.perf_counter()
        try:
            full_url = f"http://{self.cfg['ha_host']}{url}" if url.startswith("/") else url
            res = requests.get(full_url, timeout=5)
            if res.ok:
                with Image.open(BytesIO(res.content)) as raw:
                    img = raw.resize((self.w, self.w), Image.Resampling.LANCZOS)
                    processed = self.apply_kindle_filter(img)
                    self.ram_cache[cid] = processed
                    self._save_async(cpath, processed)
                    self.log("DOWNLOAD", f"下载封面成功: {cid}", (time.perf_counter() - start) * 1000)
                    return processed
        except Exception as e:
            self.log("ERR", f"封面获取失败: {e}")
        return None

    def _save_async(self, path, img):
        def run():
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path)
        threading.Thread(target=run, daemon=True).start()

    def _apply_opts(self, cmd):
        # 根据配置下发参数：如果存在则下发 waveform
        if self.wf:
            cmd["waveform"] = self.wf
        # 如果不为 0 (或 None) 则下发 nightmode
        if self.nm:
            cmd["nightmode"] = self.nm
        return cmd

    def render(self, attr):
        start = time.perf_counter()
        canvas = Image.new('L', (self.w, self.h), 255)
        draw = ImageDraw.Draw(canvas)
        
        # 1. 获取并处理元数据
        url = attr.get("entity_picture", "")
        title = attr.get("media_title", "Unknown Title")
        artist = attr.get("media_artist", "Unknown Artist")
        
        t_size, a_size = int(self.w/9), int(self.w/13)
        f_t, f_a = self.get_font(t_size), self.get_font(a_size)
        
        s_t = self.truncate(draw, title, f_t, self.w - 60)
        s_a = self.truncate(draw, artist, f_a, self.w - 60)

        # 2. 绘制全量底图（用于 screen.png 兼容性）
        cover = self._get_cover(url)
        if cover: canvas.paste(cover, (0, 0))
        draw.text((self.w // 2, self.w + 20), s_t, font=f_t, fill=0, anchor="mt")
        draw.text((self.w // 2, self.w + 110), s_a, font=f_a, fill=100, anchor="mt")

        # 3. 差异化指令构建
        cmds = []
        
        # 判断变化
        url_changed = (url != self.last_url)
        title_changed = (s_t != self.last_title)
        artist_changed = (s_a != self.last_artist)

        # 封面变化仅更新版本号
        if url_changed:
            self.last_url = url
            self.last_img_v = int(time.time())

        # 标题变化
        if title_changed:
            self.last_title = s_t
            cmds.append(self._apply_opts({
                "type": "TXT", "text": f"**{s_t}**", "top": self.w + 20, 
                "px": t_size, "use_format": True, "padding": "HORIZONTAL", 
                "center": True, "refresh": False 
            }))

        # 艺术家变化
        if artist_changed:
            self.last_artist = s_a
            cmds.append(self._apply_opts({
                "type": "TXT", "text": s_a, "top": self.w + 110, 
                "px": a_size, "padding": "HORIZONTAL", 
                "center": True, "refresh": False
            }))

        # 4. 只有当确实有变化时，才添加刷新指令并分配序号
        if cmds:
            # 追加刷新指令，移除冗余的 refresh: True
            cmds.append(self._apply_opts({"type": "REFRESH"}))
            
            # 重新分配连续序号
            for idx, c in enumerate(cmds):
                c["seq"] = idx

        self.log("RENDER", f"MusicBoard 增量渲染: {s_t}", (time.perf_counter() - start) * 1000)
        return canvas, {
            "v": int(time.time()),
            "img_v": self.last_img_v,
            "count": len(cmds),
            "commands": cmds
        }