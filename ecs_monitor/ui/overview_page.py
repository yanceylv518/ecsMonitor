"""总览页：实例卡片网格，展示各实例关键指标最新值。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.config import AppConfig
from ..core.models import InstanceInfo
from ..core.storage import Storage
from . import theme
from .format import format_rate, format_time_ago

_COLUMNS = 3


class InstanceCard(QFrame):
    double_clicked = Signal(str)

    def __init__(self, info: InstanceInfo):
        super().__init__()
        self.instance_id = info.instance_id
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._name = QLabel(info.instance_name or info.instance_id)
        self._name.setObjectName("cardName")
        self._iid = QLabel(info.instance_id)
        self._iid.setObjectName("cardId")
        self._status = QLabel()
        layout.addWidget(self._name)
        layout.addWidget(self._iid)
        layout.addWidget(self._status)
        layout.addSpacing(6)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(6)
        self._values: dict[str, QLabel] = {}
        for row, (key, label_text) in enumerate(
            [("CPUUtilization", "CPU"), ("memory_usedutilization", "内存"), ("InternetOutRate", "公网出")]
        ):
            label = QLabel(label_text)
            label.setProperty("class", "metricLabel")
            grid.addWidget(label, row, 0)
            value = QLabel("--")
            value.setProperty("class", "metricValue")
            if key == "CPUUtilization":  # CPU 是首要指标，字号更大
                value.setProperty("primary", "true")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value, row, 1)
            self._values[key] = value
        layout.addLayout(grid)

    def update_data(
        self, info: InstanceInfo, latest: dict[str, tuple[int, float]], cfg: AppConfig
    ) -> None:
        running = info.status == "Running"
        self._status.setText(("● " if running else "○ ") + info.status)
        self._status.setStyleSheet(
            f"color: {theme.GOOD if running else theme.MUTED}; font-size: 12px;"
        )

        alert = False
        thresholds = {
            "CPUUtilization": cfg.cpu_alert_threshold,
            "memory_usedutilization": cfg.mem_alert_threshold,
        }
        for metric, label in self._values.items():
            point = latest.get(metric)
            if point is None or not running:
                label.setText("--")
                self._set_prop(label, "alert", False)
                continue
            _, value = point
            if metric.endswith("Rate"):
                label.setText(format_rate(value))
            else:
                label.setText(f"{value:.1f}%")
            over = metric in thresholds and value >= thresholds[metric]
            alert = alert or over
            self._set_prop(label, "alert", over)

        self._set_prop(self, "alert", alert and running)
        self._set_prop(self, "stopped", not running)

    @staticmethod
    def _set_prop(widget: QWidget, name: str, value: bool) -> None:
        widget.setProperty(name, "true" if value else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.double_clicked.emit(self.instance_id)
        super().mouseDoubleClickEvent(event)


class OverviewPage(QWidget):
    instance_activated = Signal(str)  # 双击卡片 → 打开详情页

    def __init__(self, storage: Storage, config: AppConfig):
        super().__init__()
        self.setObjectName("page")
        self._storage = storage
        self._config = config
        self._cards: dict[str, InstanceCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        self._hint = QLabel("最近采集：--")
        self._hint.setProperty("class", "hint")
        outer.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setObjectName("page")
        self._grid = QGridLayout(container)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._empty = QLabel("暂无实例数据。请在「设置」中配置凭证，或等待首轮采集完成。")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(self._empty, 0, 0)

    def set_config(self, config: AppConfig) -> None:
        self._config = config
        self.refresh()

    def on_data_updated(self, stats: dict) -> None:
        self._hint.setText(
            f"最近采集：{format_time_ago(stats['at'])}　实例 {stats['instances']} 个，新增数据点 {stats['inserted']} 条"
        )
        self.refresh()

    def refresh(self) -> None:
        instances = self._storage.list_instances()
        latest = self._storage.latest_values()

        self._empty.setVisible(not instances)
        wanted = {i.instance_id for i in instances}
        for iid in list(self._cards):
            if iid not in wanted:
                self._cards.pop(iid).deleteLater()

        for idx, info in enumerate(instances):
            card = self._cards.get(info.instance_id)
            if card is None:
                card = InstanceCard(info)
                card.double_clicked.connect(self.instance_activated)
                self._cards[info.instance_id] = card
            self._grid.addWidget(card, idx // _COLUMNS, idx % _COLUMNS)
            card.update_data(info, latest.get(info.instance_id, {}), self._config)
