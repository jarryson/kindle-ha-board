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
        2. 如果 active_board 的 trigger_state 满足，则进入该模式。
        3. 如果所有 active_boards 都不满足且已超时，回到 default 模式。
        """
        now = time.time()
        target_board_name = self.default_board_name
        target_attr = ha_cache

        # 1. 优先级扫描
        for b_name in self.active_board_names:
            board = self.boards.get(b_name)
            if not board:
                continue

            b_cfg = board.board_cfg
            entity_id = b_cfg.get("entity_id")
            if not entity_id:
                continue

            state_data = ha_cache.get(entity_id)
            if not state_data:
                continue

            state = state_data.get("state", "unknown")
            trigger_states = b_cfg.get("trigger_state", [])

            if state in trigger_states:
                target_board_name = b_name
                target_attr = state_data.get("attributes", {})
                break

        # 2. 状态变化检测 (针对当前选中的看板)
        board = self.boards[target_board_name]

        # 模式切换逻辑：如果目标是默认看板，需检查是否超过观察期
        if target_board_name == self.default_board_name:
            if self.current_mode != self.default_board_name:
                if now - self.last_update_time <= self.timeout:
                    # 仍在观察期内，保持上一个活跃看板
                    target_board_name = self.current_mode
                    board = self.boards[target_board_name]
                else:
                    self.current_mode = self.default_board_name

        # 3. 数据有效性检查 (仅针对音乐等需要元数据的看板)
        title = target_attr.get("media_title")
        # 如果是音乐模式但没有标题，或者是缓冲期的 "None"，则跳过以防止污染缓存
        if target_board_name == "music":
            if title is None or str(title).lower() in ["none", "unknown title"]:
                return None, None

        # 4. 渲染判断
        is_mode_changed = target_board_name != self.last_board_name

        # 构造元数据快照进行比对
        metadata = {
            "title": title,
            "artist": target_attr.get("media_artist"),
            "picture": target_attr.get("entity_picture"),
            "state": target_attr.get("state"),  # 包含状态变化
        }
        is_metadata_changed = metadata != self.last_metadata

        if is_mode_changed or is_metadata_changed or force:
            self.last_board_name = target_board_name
            self.last_metadata = metadata
            self.last_update_time = now
            self.current_mode = target_board_name

            return board.render(target_attr)

        return None, None
