import time

class Coordinator:
    def __init__(self, name, config, music_board, default_board, timeout=300):
        self.name = name
        self.config = config
        self.music_board = music_board
        self.default_board = default_board
        self.timeout = timeout
        
        # 从配置中获取播放器实体 ID
        self.player_id = config.get("entity_id")
        self.current_mode = "music" # 初始模式
        
        self.last_state = None
        self.last_title = None
        self.last_artist = None
        self.last_update_time = 0
        self.refresh_interval = 300 # 强制刷新间隔（秒）

    def update(self, ha_cache, force=False):
        """
        处理从 HA 缓存收到的状态数据，由 main.py 调用
        """
        state_data = ha_cache.get(self.player_id)
        if not state_data:
            # 如果没有播放器数据，尝试运行默认看板（如图片轮播）
            self.current_mode = "default"
            return self.default_board.render(ha_cache)

        state = state_data.get("state")
        attr = state_data.get("attributes", {})
        title = attr.get("media_title")
        artist = attr.get("media_artist")

        # 🌟 核心逻辑：丢弃标题为 None 或 "None" 的情况（缓冲期数据污染）
        if title is None or str(title).lower() == "none":
            return None, None

        # 检查是否由于进度条变动导致的重复触发
        metadata_changed = (title != self.last_title or artist != self.last_artist)
        state_changed = (state != self.last_state)
        
        now = time.time()
        should_render = force

        # 模式切换逻辑
        if state == "playing":
            self.current_mode = "music"
            if metadata_changed or state_changed:
                should_render = True
        elif state in ["paused", "idle"]:
            # 如果处于暂停或空闲状态
            if state_changed:
                should_render = True
            
            # 检查超时，如果超时则切换到默认模式（例如图片展示）
            if now - self.last_update_time > self.timeout:
                self.current_mode = "default"
                return self.default_board.render(ha_cache)
        
        # 强制周期性刷新逻辑
        if now - self.last_update_time > self.refresh_interval:
            should_render = True

        if should_render:
            self.last_state = state
            self.last_title = title
            self.last_artist = artist
            self.last_update_time = now
            
            # 渲染音乐看板
            self.current_mode = "music"
            return self.music_board.render(attr)
        
        return None, None