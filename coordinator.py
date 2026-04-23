from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image

    from .scenes.base import BaseBoard


class Coordinator:
    """
    状态协调器：根据看板优先级列表和触发条件进行调度。
    """

    def __init__(
        self,
        name: str,
        device_cfg: dict[str, Any],
        boards: dict[str, BaseBoard],
        default_board_name: str,
        active_board_names: list[str],
    ):
        self.name = name
        self.device_cfg = device_cfg
        self.boards = boards
        self.default_board_name = default_board_name
        self.active_board_names = active_board_names
        self.timeout = device_cfg.get("timeout", 300)

        # 运行状态追踪
        self.current_mode: str = default_board_name
        self.last_board_name: str | None = None
        self.last_update_time: float = 0
        self.last_metadata: dict[str, Any] = {}

    def update(
        self, ha_cache: dict[str, Any], force: bool = False
    ) -> tuple[Image.Image | None, dict[str, Any] | None]:
        """
        核心调度逻辑：
        1. 按顺序检查 active_boards。
        2. 如果 active_board 的任一 entity_id 满足 trigger_state，则进入该模式。
        3. 如果所有都不满足且已超时，回到 default 模式。
        """
        now = time.time()
        target_board_name = self.default_board_name
        target_attr = {}
        target_state = "unknown"
        active_eid = None

        # 1. 优先级扫描
        for b_name in self.active_board_names:
            board = self.boards.get(b_name)
            if not board:
                continue

            b_cfg = board.board_cfg
            eids = b_cfg.get("entity_id")
            if not eids:
                continue

            # 支持字符串或列表
            if isinstance(eids, str):
                eids = [eids]

            trigger_states = b_cfg.get("trigger_state", [])

            found = False
            for eid in eids:
                state_data = ha_cache.get(eid)
                if not state_data:
                    continue

                state = state_data.get("state", "unknown")
                if state in trigger_states:
                    target_board_name = b_name
                    target_attr = state_data.get("attributes", {})
                    target_state = state
                    active_eid = eid
                    found = True
                    break

            if found:
                break

        # 2. 状态变化检测 (针对当前选中的看板)
        board = self.boards[target_board_name]

        # 模式切换逻辑
        if target_board_name == self.default_board_name:
            if self.current_mode != self.default_board_name:
                if now - self.last_update_time <= self.timeout:
                    target_board_name = self.current_mode
                    board = self.boards[target_board_name]
                else:
                    self.current_mode = self.default_board_name

        # 3. 数据有效性检查
        title = target_attr.get("media_title")
        if target_board_name == "music":
            if title is None or str(title).lower() in ["none", "unknown title"]:
                return None, None

        # 4. 渲染判断
        is_mode_changed = target_board_name != self.last_board_name

        # 构造元数据快照进行比对 (加入 entity_id 确保切换播放器时刷新)
        metadata = {
            "eid": active_eid,
            "title": title,
            "artist": target_attr.get("media_artist"),
            "picture": target_attr.get("entity_picture"),
            "state": target_state,
        }
        is_metadata_changed = metadata != self.last_metadata

        if is_mode_changed or is_metadata_changed or force:
            self.last_board_name = target_board_name
            self.last_metadata = metadata
            self.last_update_time = now
            self.current_mode = target_board_name

            return board.render(target_attr)

        return None, None
