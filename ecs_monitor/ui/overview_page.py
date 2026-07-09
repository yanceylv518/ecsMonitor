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
from .format import format_rate, format_time_ago

_COLUMNS = 3

_CARD_QSS = """
QFrame#card {
    border: 1px solid palette(mid);
    border-radius: 8px;
    background: palette(base);
}
QFrame#card[alert="true"] { border: 2px solid #d93026; }
QFrame#card[stopped="true"] { background: palette(window); }
QLabel#name { font-size: 15px; font-weight: bold; }
QLabel#iid { color: palette(placeholder-text); font-size: 11px; }
QLabel.metricValue { font-size: 14px; font-weight: 600; }
QLabel.metricValue[alert="true"] { color: #d93026; }
"""


class InstanceCard(QFrame):
    double_clicked = Signal(str)

    def __init__(self, info: InstanceInfo):
        super().__init__()
        self.instance_id = info.instance_id
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(220)

        layout = QVBoxLayout(self)
        self._name = QLabel(info.instance_name or info.instance_id)
        self._name.setObjectName("name")
        self._iid = QLabel(info.instance_id)
        self._iid.setObjectName("iid")
        self._status = QLabel()
        layout.addWidget(self._name)
        layout.addWidget(self._iid)
        layout.addWidget(self._status)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self._values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(
            [("CPUUtilization", "CPU"), ("memory_usedutilization", "内存"), ("InternetOutRate", "公网出")]
        ):
            grid.addWidget(QLabel(label), row, 0)
            value = QLabel("--")
            value.setProperty("class", "metricValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(value, row, 1)
            self._values[key] = value
        layout.addLayout(grid)

    def update_data(
        self, info: InstanceInfo, latest: dict[str, tuple[int, float]], cfg: AppConfig
    ) -> None:
        running = info.status == "Running"
        self._status.setText(("● " if running else "○ ") + info.status)
        self._status.setStyleSheet(f"color: {'#2da44e' if running else 'gray'};")

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
        self._storage = storage
        self._config = config
        self._cards: dict[str, InstanceCard] = {}
        self.setStyleSheet(_CARD_QSS)

        outer = QVBoxLayout(self)
        self._hint = QLabel("最近采集：--")
        outer.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
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
