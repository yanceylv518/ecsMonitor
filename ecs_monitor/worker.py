"""采集线程：驱动 MetricSource 定时采集并入库，通过 Qt 信号通知 UI。

线程内自建 Storage（SQLite 连接不跨线程）；面向 MetricSource 接口，
Mock 与真实数据源零改动互换。
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .core.config import AppConfig
from .core.source import MetricSource, SourceError
from .core.storage import Storage

log = logging.getLogger(__name__)

_DISCOVERY_EVERY = 10  # 每 N 轮刷新一次实例列表
_PURGE_EVERY_S = 86_400  # 过期数据清理周期


class CollectorWorker(QThread):
    data_updated = Signal(dict)  # {"inserted": int, "instances": int, "at": epoch_s}
    instances_updated = Signal(list)  # list[InstanceInfo]
    collect_error = Signal(str)  # 面向用户的错误描述
    state_changed = Signal(str)  # running / paused / stopped

    def __init__(self, source: MetricSource, config: AppConfig, db_path: str | Path):
        super().__init__()
        self._source = source
        self._db_path = db_path
        self._lock = threading.Lock()
        self._config = config
        self._wake = threading.Event()  # 打断 sleep：立即采集/退出/配置变更
        self._stop = False
        self._paused = False
        self._cycle = 0
        self._last_purge = 0.0
        self._instances: list = []

    # ---- 外部指令（UI 线程调用，线程安全） ----

    def update_config(self, config: AppConfig) -> None:
        with self._lock:
            self._config = config
        self._cycle = 0  # 触发下一轮重新发现实例
        self._wake.set()

    def collect_now(self) -> None:
        self._wake.set()

    def pause(self) -> None:
        self._paused = True
        self.state_changed.emit("paused")

    def resume(self) -> None:
        self._paused = False
        self._wake.set()
        self.state_changed.emit("running")

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    # ---- 线程主体 ----

    def run(self) -> None:
        storage = Storage(self._db_path)
        self.state_changed.emit("running")
        try:
            while not self._stop:
                if not self._paused:
                    try:
                        self._collect_once(storage)
                    except SourceError as e:
                        log.warning("采集失败: %s", e)
                        self.collect_error.emit(str(e))
                    except Exception:
                        log.error("采集异常:\n%s", traceback.format_exc())
                        self.collect_error.emit("采集出现内部错误，详见日志")
                with self._lock:
                    interval = self._config.interval_seconds
                self._wake.wait(timeout=interval)
                self._wake.clear()
        finally:
            storage.close()
            self.state_changed.emit("stopped")

    def _collect_once(self, storage: Storage) -> None:
        with self._lock:
            cfg = self._config

        # 实例发现（首轮及每 N 轮一次）
        if self._cycle % _DISCOVERY_EVERY == 0:
            discovered = self._source.list_instances()
            if cfg.instance_ids:  # 用户手动指定了实例则做筛选
                discovered = [i for i in discovered if i.instance_id in cfg.instance_ids]
            self._instances = discovered
            storage.upsert_instances(discovered)
            self.instances_updated.emit(discovered)
        self._cycle += 1

        now_ms = int(time.time() * 1000)
        ids = [i.instance_id for i in self._instances]
        inserted = 0
        if ids and cfg.metrics:
            points = self._source.fetch_metrics(
                ids, cfg.metrics, now_ms - cfg.lookback_seconds * 1000, now_ms
            )
            inserted = storage.insert_datapoints(points)

        # 每日清理过期数据
        if cfg.retention_days > 0 and time.time() - self._last_purge > _PURGE_EVERY_S:
            purged = storage.purge_older_than(cfg.retention_days)
            if purged:
                log.info("清理过期数据 %d 条", purged)
            self._last_purge = time.time()

        self.data_updated.emit(
            {"inserted": inserted, "instances": len(ids), "at": time.time()}
        )
