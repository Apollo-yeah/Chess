"""对局领域层：多对局状态模型 + 持久化 + 注册表 + 推送中心 + 业务编排。"""

from app.game.hub import GameHub, get_hub
from app.game.models import GameState, MoveRecord, evaluate_result, now_str
from app.game.registry import GameRegistry, get_registry
from app.game.service import GameService, get_service
from app.game.storage import Storage, get_storage

__all__ = [
    "GameHub",
    "GameRegistry",
    "GameState",
    "GameService",
    "MoveRecord",
    "Storage",
    "evaluate_result",
    "get_hub",
    "get_registry",
    "get_service",
    "get_storage",
    "now_str",
]
