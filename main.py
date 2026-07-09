"""ECS 监控桌面程序入口。

用法:
    python main.py            # 真实模式（阿里云 API）
    python main.py --mock     # Mock 演示模式（无需阿里云账号）

mock 与真实数据源的差异全部收敛在本文件的 source_factory 中，
UI 与采集线程只面向 MetricSource 接口。
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ecs_monitor.core import credentials
from ecs_monitor.core.aliyun_source import AliyunMetricSource
from ecs_monitor.core.config import AppConfig, data_dir, default_db_path, logs_dir
from ecs_monitor.core.mock_source import MockMetricSource
from ecs_monitor.core.source import MetricSource
from ecs_monitor.core.storage import Storage
from ecs_monitor.ui.main_window import MainWindow
from ecs_monitor.worker import CollectorWorker

log = logging.getLogger(__name__)

_MOCK_BACKFILL_S = 24 * 3600  # mock 模式启动时回填的历史数据范围


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(
            logging.handlers.TimedRotatingFileHandler(
                logs_dir() / "ecs_monitor.log", when="D", backupCount=7, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def make_source_factory(mock: bool):
    def factory(cfg: AppConfig, secret: str | None = None) -> MetricSource:
        if mock:
            return MockMetricSource()
        if secret is None:
            secret = credentials.get_secret(cfg.access_key_id) or ""
        return AliyunMetricSource(cfg.region_id, cfg.access_key_id, secret)

    return factory


def mock_backfill(source: MetricSource, storage: Storage) -> None:
    """mock 模式首次启动时回填历史数据，保证详情页时间范围切换有数可看。"""
    if storage.datapoint_count() > 0:
        return
    instances = source.list_instances()
    storage.upsert_instances(instances)
    now_ms = int(time.time() * 1000)
    points = source.fetch_metrics(
        [i.instance_id for i in instances],
        list(AppConfig().metrics),
        now_ms - _MOCK_BACKFILL_S * 1000,
        now_ms,
    )
    inserted = storage.insert_datapoints(points)
    log.info("mock 历史数据回填 %d 条", inserted)


def main() -> int:
    parser = argparse.ArgumentParser(description="阿里云 ECS 监控")
    parser.add_argument("--mock", action="store_true", help="使用 Mock 数据源（演示/开发）")
    parser.add_argument("--db", type=Path, default=None, help="指定 SQLite 数据库路径")
    args = parser.parse_args()

    setup_logging()
    config = AppConfig.load()
    db_path = args.db or (data_dir() / "mock_metrics.db" if args.mock else default_db_path())
    source_factory = make_source_factory(args.mock)
    source = source_factory(config)

    app = QApplication(sys.argv)
    app.setApplicationName("EcsMonitor")

    ui_storage = Storage(db_path)  # UI 线程读连接
    if args.mock:
        mock_backfill(source, ui_storage)

    worker = CollectorWorker(source, config, db_path)
    window = MainWindow(config, ui_storage, worker, source_factory, mock_mode=args.mock)
    worker.start()
    window.show()

    code = app.exec()
    worker.stop()
    worker.wait(5000)
    ui_storage.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
