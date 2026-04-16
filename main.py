import asyncio, json, threading, time, socket, importlib, logging
from io import BytesIO
from flask import Flask, Response, jsonify
import websockets
from requests.packages.urllib3.util import connection

# 优化局域网解析，强制 IPv4
connection.allowed_gai_family = lambda: socket.AF_INET

from coordinator import Coordinator

with open("config.json") as f:
    cfg = json.load(f)

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

class RAM:
    store = {}    # 缓存每个设备的图片和指令
    ha_cache = {} # 缓存 HA 全量状态

device_managers = {}

def log(tag, msg, duration=None):
    if not cfg.get("debug"): return
    ts = time.strftime('%H:%M:%S')
    dur_str = f" [{duration:.2f}ms]" if duration is not None else ""
    print(f"[{ts}] [MAIN_{tag}]{dur_str} {msg}")

def get_board_class(board_type):
    """根据类型字符串动态获取 Board 类，不再硬编码类名"""
    try:
        start_ts = time.perf_counter()
        module = importlib.import_module(f"scenes.{board_type}")
        # 按照统一规范寻找类：xxxBoard
        cls = getattr(module, f"{board_type.capitalize()}Board")
        log("IMPORT", f"成功加载模块 scenes.{board_type}", (time.perf_counter() - start_ts) * 1000)
        return cls
    except Exception as e:
        log("ERR", f"无法加载场景模块 {board_type}: {e}")
        return None

def init_devices():
    """完全基于配置文件初始化设备及其场景"""
    for k_name, d_cfg in cfg["devices"].items():
        layout = d_cfg.get("layout", {"width": 600, "height": 800})
        
        # 1. 加载音乐看板 (作为核心播放模式)
        MusicCls = get_board_class("music")
        
        # 2. 从配置获取默认看板类型 (不再在代码中写死 "picture")
        b_info = d_cfg.get("board", {})
        b_type = b_info.get("type")
        
        if not b_type:
            log("ERR", f"设备 [{k_name}] 未在 config 中指定 board.type，跳过初始化")
            continue
            
        DefaultCls = get_board_class(b_type)
        
        if MusicCls and DefaultCls:
            # 实例化场景并交给协调器
            m_board = MusicCls(cfg, layout, d_cfg)
            d_board = DefaultCls(cfg, b_info, layout)
            
            device_managers[k_name] = Coordinator(
                k_name, d_cfg, m_board, d_board, d_cfg.get("timeout", 300)
            )
            
            RAM.store[k_name] = {"img": b"", "st": {}, "last_seen": 0}
            log("INIT", f"设备 [{k_name}] 初始化完成 (模式: music + {b_type})")

@app.route('/<k_name>/status')
def get_status(k_name):
    if k_name in RAM.store: RAM.store[k_name]["last_seen"] = time.time()
    data = RAM.store.get(k_name)
    return jsonify(data["st"]) if data and data["st"] else (jsonify({"error": "not found"}), 404)

@app.route('/<k_name>/screen.png')
def get_image(k_name):
    data = RAM.store.get(k_name)
    if data and data["img"]:
        return Response(data["img"], mimetype='image/png')
    return ("Not Found", 404)

async def ha_worker():
    url = f"ws://{cfg['ha_host']}/api/websocket"
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"type": "auth", "access_token": cfg['ha_token']}))
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("type") == "auth_ok":
                        await ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
                        await ws.send(json.dumps({"id": 2, "type": "get_states"}))
                    
                    # 初始全量同步
                    if data.get("id") == 2:
                        for p in data.get("result", []):
                            if p: RAM.ha_cache[p["entity_id"]] = p
                        for k, coord in device_managers.items():
                            process_update(k, coord, force=True)
                    
                    # 增量事件更新
                    if data.get("type") == "event":
                        new_s = data["event"]["data"].get("new_state")
                        if not new_s: continue
                        eid = new_s["entity_id"]
                        RAM.ha_cache[eid] = new_s
                        for k, coord in device_managers.items():
                            # 若播放器状态变动或处于默认看板模式（可能有关联实体更新），触发重绘
                            if eid == coord.player_id or coord.current_mode == "default":
                                process_update(k, coord)
        except Exception as e:
            log("WS_ERR", f"WebSocket 异常: {e}")
            await asyncio.sleep(5)

def process_update(k_name, coord, force=False):
    """执行渲染流程并更新内存缓存"""
    start_ts = time.perf_counter()
    img, st = coord.update(RAM.ha_cache, force=force)
    if img:
        buf = BytesIO()
        img.save(buf, format="PNG")
        RAM.store[k_name].update({"img": buf.getvalue(), "st": st})
        log("UPDATE", f"设备 [{k_name}] 画面已更新", (time.perf_counter() - start_ts) * 1000)

if __name__ == "__main__":
    init_devices()
    
    # 线程: WebSocket 监听 HA 状态
    threading.Thread(target=lambda: asyncio.run(ha_worker()), daemon=True).start()
    
    # 线程: 定时兜底更新
    def timer_task():
        while True:
            for k, c in device_managers.items(): process_update(k, c)
            time.sleep(30)
    threading.Thread(target=timer_task, daemon=True).start()
    
    log("START", f"服务运行中，端口: {cfg['server_port']}")
    app.run(host='0.0.0.0', port=cfg['server_port'], debug=False, use_reloader=False)