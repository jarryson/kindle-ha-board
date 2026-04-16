import time
from pathlib import Path
from PIL import Image, ImageFont

# 🌟 统一路径管理
class DataPaths:
    """数据路径常量"""
    DATA_ROOT = Path("data")
    DATA_CONFIG = DATA_ROOT / "config.json"
    DATA_PICTURES = DATA_ROOT / "pictures"
    
    CACHE_ROOT = Path("cache")
    CACHE_COVERS = CACHE_ROOT / "covers"
    CACHE_PICTURES = CACHE_ROOT / "pictures"
    
    @classmethod
    def ensure_dirs(cls):
        """确保所有必要的目录存在"""
        cls.ROOT.mkdir(exist_ok=True)
        cls.PICTURES.mkdir(parents=True, exist_ok=True)
        cls.CACHE_ROOT.mkdir(exist_ok=True)
        cls.CACHE_COVERS.mkdir(parents=True, exist_ok=True)
        cls.CACHE_PICTURES.mkdir(parents=True, exist_ok=True)

class BaseBoard:
    def __init__(self, config, layout):
        self.cfg = config
        self.debug = config.get("debug", False)
        self.w, self.h = layout['width'], layout['height']
        
        self.cache_root = DataPaths.CACHE_ROOT
        self.cache_root.mkdir(exist_ok=True)
        self.ram_cache = {} 

    def log(self, tag, msg, duration=None):
        """统一计时日志输出"""
        if not self.debug: return
        ts = time.strftime('%H:%M:%S')
        dur_str = f" [{duration:.2f}ms]" if duration is not None else ""
        print(f"[{ts}] [{tag}]{dur_str} {msg}")

    def apply_kindle_filter(self, img):
        """核心：16级灰度抖动处理 (耗时操作)"""
        start = time.perf_counter()
        res = img.convert('L').quantize(colors=16, dither=Image.FLOYDSTEINBERG).convert('L')
        self.log("FILTER", "16级灰度抖动处理完成", (time.perf_counter() - start) * 1000)
        return res

    def get_font(self, size):
        try:
            return ImageFont.truetype(self.cfg['font_path'], size, index=self.cfg['font_index'])
        except Exception as e:
            self.log("FONT", f"字体加载失败: {e}")
            return ImageFont.load_default()

    def truncate(self, draw, text, font, max_w):
        """文本截断处理，确保最终只有一行且不超出宽度"""
        if not text:
            return ""
            
        # 🌟 核心修改：强制移除换行符并合并多余空格，确保输出绝对只有一行
        text = " ".join(text.replace('\n', ' ').replace('\r', ' ').split())
        
        # 如果当前长度已经符合要求，直接返回
        if draw.textlength(text, font) <= max_w:
            return text
            
        # 否则从末尾开始截断并添加省略号，直到长度符合 max_w
        t = text
        # 循环直到截断后的文本加省略号宽度小于等于最大宽度
        while t and draw.textlength(t + "..", font) > max_w:
            t = t[:-1]
            
        return t.strip() + ".."