"""应用配置：JSON 读写与存储路径约定。

Windows 下数据目录为 %APPDATA%\\EcsMonitor，其他平台回退 ~/.config/EcsMonitor。
AccessKey Secret 不在配置文件中（见 credentials.py）。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import DEFAULT_METRICS

APP_NAME = "EcsMonitor"


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.json"


def default_db_path() -> Path:
    return data_dir() / "ecs_metrics.db"


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class AppConfig:
    region_id: str = "cn-hangzhou"
    access_key_id: str = ""  # Secret 存 keyring，不落文件
    instance_ids: list[str] = field(default_factory=list)  # 空 = 自动发现
    interval_seconds: int = 60
    period: int = 60  # 云监控聚合粒度（秒）
    lookback_seconds: int = 300  # 采集回看窗口，与上轮重叠防漏点
    retention_days: int = 30  # 0 = 永久保留
    metrics: list[str] = field(default_factory=lambda: list(DEFAULT_METRICS))
    cpu_alert_threshold: float = 90.0
    mem_alert_threshold: float = 90.0
    start_minimized: bool = False
    auto_start: bool = False

    def validate(self) -> None:
        if self.interval_seconds < 10:
            raise ValueError("采集间隔不能小于 10 秒")
        if self.period < 15:
            raise ValueError("聚合粒度不能小于 15 秒")
        if self.lookback_seconds < self.period:
            raise ValueError("回看窗口不能小于聚合粒度")

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        """读取配置；文件不存在或字段缺失时使用默认值。"""
        p = path or config_path()
        cfg = cls()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            known = {f for f in cfg.__dataclass_fields__}
            for k, v in data.items():
                if k in known:
                    setattr(cfg, k, v)
        cfg.validate()
        return cfg

    def save(self, path: Path | None = None) -> None:
        self.validate()
        p = path or config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
