import json, time, zlib
from pathlib import Path
from PIL import Image
from .base import BaseBoard, DataPaths

class PictureBoard(BaseBoard):
    def __init__(self, config, b_cfg, layout):
        super().__init__(config, layout)
        self.src_dir = DataPaths.DATA_PICTURES
        self.cache_dir = DataPaths.CACHE_PICTURES
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.interval = b_cfg.get("interval", 1800)
        self.wf = b_cfg.get("waveform", "AUTO")
        self.nm = b_cfg.get("nightmode_type", 0)
        
        self.last_switch = 0
        self.last_img_v = 0
        self.index = 0
        self.playlist = []
        self._scan()

    def _scan(self):
        start = time.perf_counter()
        files = sorted([f for f in self.src_dir.glob("*") if f.suffix.lower() in ('.jpg', '.png', '.jpeg')])
        self.playlist = []
        for f in files:
            crc = 0
            with open(f, 'rb') as rb:
                while chunk := rb.read(65536): crc = zlib.crc32(chunk, crc)
            self.playlist.append({"path": str(f), "hash": "%08x" % (crc & 0xFFFFFFFF)})
        self.log("SCAN", f"同步播放列表 ({len(self.playlist)}张)", (time.perf_counter() - start) * 1000)

    def _get_image(self, item):
        cpath = self.cache_dir / f"{item['hash']}.png"
        if cpath.exists(): return Image.open(cpath)

        start = time.perf_counter()
        with Image.open(item['path']) as img:
            ir, tr = img.width/img.height, self.w/self.h
            if ir > tr:
                nw = int(tr * img.height)
                img = img.crop(((img.width-nw)//2, 0, (img.width+nw)//2, img.height))
            else:
                nh = int(img.width / tr)
                img = img.crop((0, (img.height-nh)//2, img.width, (img.height+nh)//2))
            
            img = img.resize((self.w, self.h), Image.Resampling.LANCZOS)
            processed = self.apply_kindle_filter(img)
            processed.save(cpath)
            self.log("DISK_IO", f"处理并生成新缓存: {item['hash']}", (time.perf_counter() - start) * 1000)
            return processed

    def render(self, ha_cache):
        now = time.time()
        if not self.playlist: return None, None

        if self.last_switch != 0 and (now - self.last_switch <= self.interval):
            return None, None

        if self.last_switch != 0:
            self.index = (self.index + 1) % len(self.playlist)
            
        self.last_switch = now
        self.last_img_v = int(now)
        item = self.playlist[self.index]
        canvas = self._get_image(item)
        
        cmd = {"type": "IMG", "flash": True, "refresh": True}
        # 仅在非默认时添加参数
        wf = "GC16" if self.wf == "AUTO" else self.wf
        if wf != "AUTO": cmd["waveform"] = wf
        if self.nm != 0: cmd["nightmode"] = self.nm

        return canvas, {
            "v": self.last_img_v,
            "img_v": self.last_img_v,
            "commands": [cmd]
        }