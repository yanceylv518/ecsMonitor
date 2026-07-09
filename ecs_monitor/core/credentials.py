"""AccessKey Secret 存取：优先系统凭据管理器（keyring），不落明文文件。

回退顺序：keyring → 环境变量 ALIBABA_CLOUD_ACCESS_KEY_SECRET（只读，开发用）。
keyring 后端不可用（如无桌面会话的 Linux）时写入仅保存在进程内存。
"""
from __future__ import annotations

import logging
import os

_SERVICE = "EcsMonitor"
_ENV_SECRET = "ALIBABA_CLOUD_ACCESS_KEY_SECRET"

log = logging.getLogger(__name__)
_memory_fallback: dict[str, str] = {}


def get_secret(access_key_id: str) -> str | None:
    try:
        import keyring

        secret = keyring.get_password(_SERVICE, access_key_id)
        if secret:
            return secret
    except Exception as e:  # keyring 后端不可用
        log.debug("keyring 不可用: %s", e)
    if access_key_id in _memory_fallback:
        return _memory_fallback[access_key_id]
    return os.environ.get(_ENV_SECRET) or None


def set_secret(access_key_id: str, secret: str) -> bool:
    """返回 True 表示已持久化；False 表示仅保存在内存（keyring 不可用）。"""
    try:
        import keyring

        keyring.set_password(_SERVICE, access_key_id, secret)
        return True
    except Exception as e:
        log.warning("keyring 不可用，Secret 仅保存在本次运行内存中: %s", e)
        _memory_fallback[access_key_id] = secret
        return False


def delete_secret(access_key_id: str) -> None:
    _memory_fallback.pop(access_key_id, None)
    try:
        import keyring

        keyring.delete_password(_SERVICE, access_key_id)
    except Exception:
        pass
