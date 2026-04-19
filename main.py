import asyncio
import gc
import importlib
import json
import logging
import os
import socket
import time
from io import BytesIO
from typing import Any

import aiohttp
from aiohttp import web
from urllib3.util import connection

from coordinator import Coordinator
from scenes.base import DataPaths

VERSION = os.getenv("APP_VERSION", "1.4.1")

# 优化: 强制使用 IPv4
connection.allowed_gai_family = lambda: socket.AF_INET

# 加载配置
try:
    with open(DataPaths.DATA_CONFIG, encoding="utf-8") as f:
        cfg: dict[str, Any] = json.load(f)
except FileNotFoundError:
    print(f"错误: 找不到配置文件 {DataPaths.DATA_CONFIG}")
    exit(1)

# 禁用 aiohttp 访问日志以节省 IO
logging.basicConfig(level=logging.ERROR)


class RAM:
    """运行时内存缓存"""

    store: dict[str, dict[str, Any]] = {}
    ha_cache: dict[str, Any] = {}


device_managers: dict[str, Coordinator] = {}


def log(tag: str, msg: str, duration: float | None = None) -> None:
    if not cfg.get("debug"):
        return
    dur = f" [{duration:.2f}ms]" if duration is not None else ""
    print(f"[{time.strftime('%H:%M:%S')}] [MAIN_{tag}]{dur} {msg}")


def get_board_class(board_type: str) -> Any:
    try:
        mod = importlib.import_module(f"scenes.{board_type}")
        return getattr(mod, f"{board_type.capitalize()}Board")
    except (ImportError, AttributeError) as e:
        log("ERR", f"加载场景 {board_type} 失败: {e}")
        return None


def init_devices() -> None:
    for name, d_cfg in cfg.get("devices", {}).items():
        layout = d_cfg.get("layout", {"width": 600, "height": 800})

        default_b_name = d_cfg.get("default_board", "picture")
        requested_active = d_cfg.get("active_boards", ["music"])

        # 1. 识别所有需要加载的面板名称
        all_requested = list(set([default_b_name] + requested_active))
        boards = {}

        for b_name in all_requested:
            b_cls = get_board_class(b_name)
            if not b_cls:
                log("WARN", f"跳过设备 [{name}] 的未知看板: {b_name}")
                continue

            b_cfg = d_cfg.get(b_name, {})
            boards[b_name] = b_cls(cfg, b_cfg, layout)

        # 2. 检查默认看板是否存在
        if default_b_name not in boards:
            log(
                "ERR", f"设备 [{name}] 的默认看板 {default_b_name} 加载失败，跳过该设备"
            )
            continue

        # 3. 过滤出有效的活跃看板列表 (保持原配置顺序)
        valid_active = [b for b in requested_active if b in boards]

        device_managers[name] = Coordinator(
            name, d_cfg, boards, default_b_name, valid_active
        )
        RAM.store[name] = {"img": b"", "st": {}, "last_seen": 0}
        log(
            "INIT",
            f"设备 [{name}] 已就绪 (默认: {default_b_name}, 活跃: {valid_active})",
        )


def process_update(name: str, coord: Coordinator, force: bool = False) -> None:
    """渲染任务"""
    start = time.perf_counter()
    img, st = coord.update(RAM.ha_cache, force=force)
    if img:
        buf = BytesIO()
        img.save(buf, format="PNG")
        RAM.store[name].update(
            {"img": buf.getvalue(), "st": st, "last_seen": int(time.time())}
        )
        log("RENDER", f"[{name}] 更新成功", (time.perf_counter() - start) * 1000)

        # 🌟 内存优化：处理大图后立即建议垃圾回收
        gc.collect()


# --- Aiohttp 路由处理器 ---
async def handle_status(request: web.Request) -> web.Response:
    name = request.match_info.get("name", "")
    data = RAM.store.get(name)
    if data:
        return web.json_response(data["st"])
    return web.json_response({"error": "not found"}, status=404)


async def handle_image(request: web.Request) -> web.Response:
    name = request.match_info.get("name", "")
    data = RAM.store.get(name)
    if data and data["img"]:
        return web.Response(body=data["img"], content_type="image/png")
    return web.Response(text="Not Found", status=404)


# --- 后台异步任务 ---
async def ha_worker(app: web.Application) -> None:
    url = f"ws://{cfg['ha_host']}/api/websocket"
    session = aiohttp.ClientSession()

    while True:
        try:
            async with session.ws_connect(url) as ws:
                await ws.send_json({"type": "auth", "access_token": cfg["ha_token"]})

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        d = msg.json()
                        msg_type = d.get("type")

                        if msg_type == "auth_ok":
                            await ws.send_json(
                                {
                                    "id": 1,
                                    "type": "subscribe_events",
                                    "event_type": "state_changed",
                                }
                            )
                            await ws.send_json({"id": 2, "type": "get_states"})

                        elif d.get("id") == 2:
                            for p in d.get("result", []):
                                if p and "entity_id" in p:
                                    RAM.ha_cache[p["entity_id"]] = p
                            for k, c in device_managers.items():
                                asyncio.create_task(
                                    asyncio.to_thread(process_update, k, c, force=True)
                                )

                        elif msg_type == "event":
                            new_s = d["event"]["data"].get("new_state")
                            if not new_s:
                                continue
                            eid = new_s["entity_id"]
                            RAM.ha_cache[eid] = new_s
                            for k, c in device_managers.items():
                                # 触发逻辑由 Coordinator.update 处理，这里只需触发相关设备的更新
                                asyncio.create_task(
                                    asyncio.to_thread(process_update, k, c)
                                )

                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        except Exception as e:
            log("WS_ERR", f"连接异常: {e}")
            await asyncio.sleep(5)
    await session.close()


async def timer_task(app: web.Application) -> None:
    while True:
        await asyncio.sleep(30)
        await asyncio.gather(
            *(
                asyncio.to_thread(process_update, k, c)
                for k, c in device_managers.items()
            )
        )


async def start_background_tasks(app: web.Application) -> None:
    app["ha_worker"] = asyncio.create_task(ha_worker(app))
    app["timer"] = asyncio.create_task(timer_task(app))


async def cleanup_background_tasks(app: web.Application) -> None:
    app["ha_worker"].cancel()
    app["timer"].cancel()
    await asyncio.gather(app["ha_worker"], app["timer"], return_exceptions=True)


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes(
        [
            web.get("/{name}/status", handle_status),
            web.get("/{name}/screen.png", handle_image),
        ]
    )
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app


if __name__ == "__main__":
    DataPaths.ensure_dirs()
    log("SYSTEM", f"Kindle-HABoard v{VERSION} 启动中...")
    init_devices()
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=cfg["server_port"], access_log=None)
