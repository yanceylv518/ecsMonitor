"""详情页：单实例多指标历史曲线（pyqtgraph 分组子图，共享时间轴）。"""
from __future__ import annotations

import time

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import METRICS, InstanceInfo
from ..core.storage import Storage

_RANGES = [("1h", 3600), ("6h", 6 * 3600), ("24h", 24 * 3600), ("7d", 7 * 24 * 3600)]
_MAX_POINTS = 2000  # 单条曲线超过该点数则降采样

# 子图分组：(标题, Y 轴单位, 该组指标)
_GROUPS = [
    ("CPU / 内存 (%)", "%", ["CPUUtilization", "memory_usedutilization", "diskusage_utilization"]),
    ("网络 (bps)", "bps", ["InternetInRate", "InternetOutRate", "IntranetInRate", "IntranetOutRate"]),
    ("磁盘 (B/s)", "B/s", ["DiskReadBPS", "DiskWriteBPS"]),
]

_COLORS = ["#4285f4", "#ea4335", "#fbbc04", "#34a853", "#a142f4", "#f47c3c"]


class DetailPage(QWidget):
    def __init__(self, storage: Storage):
        super().__init__()
        self._storage = storage
        self._range_s = 3600

        pg.setConfigOptions(antialias=True, background=None, foreground="d")

        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("实例:"))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(260)
        self._combo.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self._combo)
        bar.addStretch()

        self._range_group = QButtonGroup(self)
        for label, seconds in _RANGES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(seconds == self._range_s)
            btn.clicked.connect(lambda _, s=seconds: self._set_range(s))
            self._range_group.addButton(btn)
            bar.addWidget(btn)
        layout.addLayout(bar)

        self._graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self._graphics)
        self._plots: list[pg.PlotItem] = []
        first: pg.PlotItem | None = None
        for row, (title, _unit, _metrics) in enumerate(_GROUPS):
            plot = self._graphics.addPlot(
                row=row, col=0, title=title, axisItems={"bottom": pg.DateAxisItem()}
            )
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.addLegend(offset=(10, 5))
            if first is None:
                first = plot
            else:
                plot.setXLink(first)
            self._plots.append(plot)

        self._empty = QLabel("暂无数据")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        layout.addWidget(self._empty)

    # ---- 外部接口 ----

    def set_instances(self, instances: list[InstanceInfo]) -> None:
        current = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        for info in instances:
            self._combo.addItem(f"{info.instance_name} ({info.instance_id})", info.instance_id)
        if current is not None:
            idx = self._combo.findData(current)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self.refresh()

    def select_instance(self, instance_id: str) -> None:
        idx = self._combo.findData(instance_id)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)  # 触发 refresh

    def refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

    # ---- 内部 ----

    def _set_range(self, seconds: int) -> None:
        self._range_s = seconds
        self.refresh()

    def refresh(self) -> None:
        iid = self._combo.currentData()
        if iid is None:
            self._empty.show()
            return

        end_ms = int(time.time() * 1000)
        start_ms = end_ms - self._range_s * 1000
        all_metrics = [m for _, _, group in _GROUPS for m in group]
        series = self._storage.query_range(iid, all_metrics, start_ms, end_ms)
        has_data = any(series.values())
        self._empty.setVisible(not has_data)

        color_index = 0
        for plot, (_title, _unit, metrics) in zip(self._plots, _GROUPS):
            plot.clearPlots()
            for metric in metrics:
                points = series.get(metric, [])
                color = _COLORS[color_index % len(_COLORS)]
                color_index += 1
                if not points:
                    continue
                if len(points) > _MAX_POINTS:  # 大范围降采样
                    stride = len(points) // _MAX_POINTS + 1
                    points = points[::stride]
                xs = [ts / 1000 for ts, _ in points]
                ys = [v for _, v in points]
                meta = METRICS.get(metric)
                plot.plot(
                    xs, ys,
                    pen=pg.mkPen(color, width=1.6),
                    name=meta.label if meta else metric,
                )
            plot.setXRange(start_ms / 1000, end_ms / 1000, padding=0.02)
