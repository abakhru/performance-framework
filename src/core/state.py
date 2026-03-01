"""core/state.py — Shared mutable application state, safe to import from any module."""

from core.storage import build_op_group, load_endpoint_config
from core.storage import save_endpoints_json as _save_storage


class AppState:
    """Holds endpoint config and derived op-group mappings with thread-safe refs."""

    def __init__(self) -> None:
        self.endpoint_config: dict = load_endpoint_config()
        self.op_group: dict = build_op_group(self.endpoint_config)
        # Mutable single-element lists used by lifecycle threads for late binding
        self.ep_cfg_ref: list = [self.endpoint_config]
        self.op_group_ref: list = [self.op_group]

    def save_endpoints(self, config: dict) -> None:
        _save_storage(config)
        self.endpoint_config = config
        self.op_group = build_op_group(config)
        self.ep_cfg_ref[0] = config
        self.op_group_ref[0] = self.op_group


state = AppState()
