"""主窗口：侧边导航 + 三页（总览/详情/设置），连接采集线程信号。"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from ..core.config import AppConfig
from ..core.storage import Storage
from ..worker import CollectorWorker
from .detail_page import DetailPage
from .format import format_time_ago
from .overview_page import OverviewPage
from .settings_page import SettingsPage, SourceFactory


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: AppConfig,
        storage: Storage,  # UI 线程专用的读连接
        worker: CollectorWorker,
        source_factory: SourceFactory,
        mock_mode: bool = False,
    ):
        super().__init__()
        self._worker = worker
        title = "ECS 监控"
        if mock_mode:
            title += "（Mock 演示模式）"
        self.setWindowTitle(title)
        self.resize(1080, 720)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._nav = QListWidget()
        self._nav.setFixedWidth(140)
        self._nav.setIconSize(QSize(20, 20))
        for name in ("总览", "详情", "设置"):
            QListWidgetItem(name, self._nav)
        self._nav.setCurrentRow(0)

        self._pages = QStackedWidget()
        self.overview = OverviewPage(storage, config)
        self.detail = DetailPage(storage)
        self.settings = SettingsPage(config, source_factory)
        for page in (self.overview, self.detail, self.settings):
            self._pages.addWidget(page)

        layout.addWidget(self._nav)
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self._status_label = QLabel("等待首轮采集…")
        status.addWidget(self._status_label)
        self.setStatusBar(status)

        # 导航与页面联动
        self._nav.currentRowChanged.connect(self._on_nav)
        self.overview.instance_activated.connect(self._open_detail)

        # 采集线程信号
        worker.data_updated.connect(self._on_data_updated)
        worker.instances_updated.connect(self.detail.set_instances)
        worker.collect_error.connect(self._on_error)
        worker.state_changed.connect(self._on_state)

        # 设置保存 → 热更新采集线程
        self.settings.config_saved.connect(self._on_config_saved)

        # 首次启动无凭证且非 mock 模式 → 直接进设置页
        if not mock_mode and not config.access_key_id:
            self._nav.setCurrentRow(2)
            self._status_label.setText("请先在「设置」中配置阿里云凭证")

    # ---- slots ----

    def _on_nav(self, row: int) -> None:
        self._pages.setCurrentIndex(row)
        if row == 1:
            self.detail.refresh()

    def _open_detail(self, instance_id: str) -> None:
        self._nav.setCurrentRow(1)
        self.detail.select_instance(instance_id)

    def _on_data_updated(self, stats: dict) -> None:
        self._status_label.setText(
            f"最近采集 {format_time_ago(stats['at'])}：{stats['instances']} 个实例，新增 {stats['inserted']} 条"
        )
        self.overview.on_data_updated(stats)
        self.detail.refresh_if_visible()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"⚠️ {message}")

    def _on_state(self, state: str) -> None:
        if state == "paused":
            self._status_label.setText("采集已暂停")

    def _on_config_saved(self, cfg: AppConfig) -> None:
        self.overview.set_config(cfg)
        self._worker.update_config(cfg)

    def closeEvent(self, event) -> None:  # noqa: N802
        # 阶段 4 改为最小化到托盘；当前直接退出并停止采集线程
        self._worker.stop()
        self._worker.wait(5000)
        super().closeEvent(event)
