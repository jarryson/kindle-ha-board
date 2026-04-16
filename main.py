# Version: 1.1 (Modified: Config Path)
import asyncio
import importlib
import json
import logging
import socket
import threading
import time
from io import BytesIO

import websockets
from flask import Flask, Response, jsonify
from urllib3.util import connection

from coordinator import Coordinator
from scenes.base import DataPaths

# 强制使用 IPv4 解决部分环境下的连接延迟
connection.allowed_gai_family = lambda: socket.AF_INET

try:
    with open(DataPaths.DATA_CONFIG) as f:
        cfg = json.load(f)
except FileNotFoundError:
    print(f"错误: 找不到配置文件 {DataPaths.DATA_CONFIG}")
    exit(1)

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


class RAM:
    store = {}
    ha_cache = {}


device_managers = {}


def log(tag, msg, duration=None):
    if not cfg.get("debug"):
        return
    ts = time.strftime("%H:%M:%S")
    dur = f" [{duration:.2f}ms]" if duration is not None else ""
    print(f"[{ts}] [MAIN_{tag}]{dur} {msg}")


def get_board_class(board_type):
    try:
        mod = importlib.import_module(f"scenes.{board_type}")
        cls = getattr(mod, f"{board_type.capitalize()}Board")
        return cls
    except Exception as e:
        log("ERR", f"无法加载场景 {board_type}: {e}")
        return None


def init_devices():
    for k_name, d_cfg in cfg["devices"].items():
        layout = d_cfg.get("layout", {"width": 600, "height": 800})
        MusicCls = get_board_class("music")
        b_info = d_cfg.get("board", {})
        DefaultCls = get_board_class(b_info.get("type"))

        if MusicCls and DefaultCls:
            m_board = MusicCls(cfg, layout, d_cfg)
            d_board = DefaultCls(cfg, b_info, layout)
            device_managers[k_name] = Coordinator(
                k_name, d_cfg, m_board, d_board, d_cfg.get("timeout", 300)
            )
            RAM.store[k_name] = {"img": b"", "st": {}, "last_seen": 0}
            log("INIT", f"设备 [{k_name}] 初始化完成")


def process_update(k_name, coord, force=False):
    start = time.perf_counter()
    img, st = coord.update(RAM.ha_cache, force=force)
    if img:
        buf = BytesIO()
        img.save(buf, format="PNG")
        RAM.store[k_name].update({"img": buf.getvalue(), "st": st})
        log("RENDER", f"[{k_name}] 周期刷新成功", (time.perf_counter() - start) * 1000)


@app.route("/<k_name>/status")
def get_status(k_name):
    data = RAM.store.get(k_name)
    return jsonify(data["st"]) if data else (jsonify({"error": "not found"}), 404)


@app.route("/<k_name>/screen.png")
def get_image(k_name):
    data = RAM.store.get(k_name)
    return (
        Response(data["img"], mimetype="image/png")
        if data and data["img"]
        else ("Not Found", 404)
    )


async def ha_worker():
    url = f"ws://{cfg['ha_host']}/api/websocket"
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(
                    json.dumps({"type": "auth", "access_token": cfg["ha_token"]})
                )
                async for msg in ws:
                    d = json.loads(msg)
                    if d.get("type") == "auth_ok":
                        await ws.send(
                            json.dumps(
                                {
                                    "id": 1,
                                    "type": "subscribe_events",
                                    "event_type": "state_changed",
                                }
                            )
                        )
                        await ws.send(json.dumps({"id": 2, "type": "get_states"}))
                    if d.get("id") == 2:
                        for p in d.get("result", []):
                            if p:
                                RAM.ha_cache[p["entity_id"]] = p
                        for k, c in device_managers.items():
                            process_update(k, c, force=True)
                    if d.get("type") == "event":
                        new_s = d["event"]["data"].get("new_state")
                        if not new_s:
                            continue
                        eid = new_s["entity_id"]
                        RAM.ha_cache[eid] = new_s
                        for k, c in device_managers.items():
                            if eid == c.player_id or c.current_mode == "default":
                                process_update(k, c)
        except Exception as e:
            log("WS_ERR", e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    init_devices()
    threading.Thread(target=lambda: asyncio.run(ha_worker()), daemon=True).start()

    def timer():
        while True:
            for k, c in device_managers.items():
                process_update(k, c)
            time.sleep(30)

    threading.Thread(target=timer, daemon=True).start()
    app.run(host="0.0.0.0", port=cfg["server_port"], debug=False, use_reloader=False)
