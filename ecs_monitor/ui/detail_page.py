"""详情页：单实例监控曲线，按度量拆分为独立面板。

每个面板 = 统计头部（当前值、峰值、平均、最低）+ 专属曲线图。
使用率类指标各自成图（避免多曲线互相干扰）；网络、磁盘吞吐
因单位一致且需要对比，各自合并为一图并配图例。
"""
from __future__ import annotations

import time
from bisect import bisect_left
from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import METRICS, InstanceInfo
from ..core.storage import Storage
from . import theme
from .format import format_bytes_rate, format_rate

_RANGES = [("1h", 3600), ("6h", 6 * 3600), ("24h", 24 * 3600), ("7d", 7 * 24 * 3600)]
_MAX_POINTS = 2000  # 单条曲线超过该点数则降采样

# 面板定义：(标题, 单位, 指标列表)。单指标面板显示峰值标记与统计；
# 多指标面板（单位一致、需对比）显示图例与每序列当前值。
_PANELS = [
    ("CPU 使用率", "%", ["CPUUtilization"]),
    ("内存使用率", "%", ["memory_usedutilization"]),
    ("磁盘使用率", "%", ["diskusage_utilization"]),
    ("网络带宽", "bps", ["InternetInRate", "InternetOutRate", "IntranetInRate", "IntranetOutRate"]),
    ("磁盘吞吐", "Bps", ["DiskReadBPS", "DiskWriteBPS"]),
]


def _fmt(unit: str, value: float) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "Bps":
        return format_bytes_rate(value)
    return format_rate(value)


def _fmt_tick(unit: str, value: float) -> str:
    """Y 轴刻度：紧凑格式（10M、1.5G），避免科学计数法。"""
    if unit == "%":
        return f"{value:.0f}"
    for suffix in ("", "K", "M", "G", "T"):
        if abs(value) < 1000:
            return f"{value:g}{suffix}"
        value /= 1000
    return f"{value:g}P"


class _ValueAxis(pg.AxisItem):
    def __init__(self, unit: str):
        super().__init__(orientation="left")
        self._unit = unit

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        return [_fmt_tick(self._unit, v) for v in values]


class MetricPanel(QFrame):
    """一个度量的完整展示单元：统计头部 + 曲线图。"""

    def __init__(self, title: str, unit: str, metric_names: list[str]):
        super().__init__()
        self.setObjectName("panel")
        self._unit = unit
        self._metrics = metric_names
        self._series: dict[str, list[tuple[int, float]]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # 头部第一行：标题 + 悬浮读数
        row1 = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        self._hover = QLabel("")
        self._hover.setObjectName("hoverReadout")
        row1.addWidget(title_label)
        row1.addStretch()
        row1.addWidget(self._hover)
        layout.addLayout(row1)

        # 头部第二行：当前值（大字）+ 统计信息 / 多序列当前值
        row2 = QHBoxLayout()
        self._current = QLabel("--")
        self._current.setObjectName("panelCurrent")
        self._stats = QLabel("")
        self._stats.setProperty("class", "panelStat")
        self._chips = QLabel("")  # 多序列：彩色圆点 + 当前值
        self._chips.setTextFormat(Qt.TextFormat.RichText)
        row2.addWidget(self._current)
        row2.addWidget(self._chips)
        row2.addStretch()
        row2.addWidget(self._stats)
        layout.addLayout(row2)

        # 曲线图
        self._plot = pg.PlotWidget(
            axisItems={"bottom": pg.DateAxisItem(), "left": _ValueAxis(unit)}
        )
        self._plot.setBackground(theme.SURFACE)
        self._plot.setFixedHeight(190 if len(metric_names) == 1 else 220)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.35)
        for side in ("bottom", "left"):
            axis = self._plot.getAxis(side)
            axis.setPen(pg.mkPen(theme.GRID))
            axis.setTextPen(pg.mkPen(theme.MUTED))
        # 多序列的图例由头部彩点标签承担（避免图内图例框遮挡曲线）
        self._vline = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.MUTED, style=Qt.PenStyle.DashLine))
        self._vline.hide()
        self._plot.addItem(self._vline, ignoreBounds=True)
        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        layout.addWidget(self._plot)

    # ---- 数据更新 ----

    def update_data(self, series: dict[str, list[tuple[int, float]]], start_ms: int, end_ms: int) -> None:
        self._series = {m: series.get(m, []) for m in self._metrics}
        has_data = any(self._series.values())
        self.setVisible(has_data)
        if not has_data:
            return

        plot_item = self._plot.getPlotItem()
        plot_item.clearPlots()
        for item in list(plot_item.items):
            if isinstance(item, (pg.ScatterPlotItem, pg.TextItem)):
                plot_item.removeItem(item)

        peak_all = 0.0
        for idx, metric in enumerate(self._metrics):
            points = self._series[metric]
            if not points:
                continue
            if len(points) > _MAX_POINTS:
                points = points[:: len(points) // _MAX_POINTS + 1]
            xs = [ts / 1000 for ts, _ in points]
            ys = [v for _, v in points]
            peak_all = max(peak_all, max(ys))
            color = theme.SERIES[idx % len(theme.SERIES)]
            single = len(self._metrics) == 1
            self._plot.plot(
                xs, ys,
                pen=pg.mkPen(color, width=2),
                fillLevel=0 if single else None,
                brush=pg.mkBrush(color + "22") if single else None,
            )
            # 末点标识（当前值位置）
            last_dot = pg.ScatterPlotItem(
                [xs[-1]], [ys[-1]], size=7, brush=pg.mkBrush(color), pen=pg.mkPen("w", width=1.5)
            )
            plot_item.addItem(last_dot)
            # 峰值标识（单序列面板）
            if single:
                peak_i = max(range(len(ys)), key=ys.__getitem__)
                peak_dot = pg.ScatterPlotItem(
                    [xs[peak_i]], [ys[peak_i]], size=8,
                    brush=pg.mkBrush(theme.SURFACE), pen=pg.mkPen(color, width=2),
                )
                plot_item.addItem(peak_dot)
                peak_text = pg.TextItem(
                    f"峰值 {_fmt(self._unit, ys[peak_i])}", color=theme.INK_2, anchor=(0.5, 1.3)
                )
                peak_text.setPos(xs[peak_i], ys[peak_i])
                plot_item.addItem(peak_text)

        # 头部统计
        if len(self._metrics) == 1:
            points = self._series[self._metrics[0]]
            values = [v for _, v in points]
            self._current.setText(_fmt(self._unit, values[-1]))
            self._stats.setText(
                f"峰值 {_fmt(self._unit, max(values))} ・ "
                f"平均 {_fmt(self._unit, sum(values) / len(values))} ・ "
                f"最低 {_fmt(self._unit, min(values))}"
            )
            self._current.show()
            self._chips.hide()
        else:
            chips = []
            for idx, metric in enumerate(self._metrics):
                points = self._series[metric]
                if not points:
                    continue
                meta = METRICS.get(metric)
                color = theme.SERIES[idx % len(theme.SERIES)]
                chips.append(
                    f'<span style="color:{color}; font-size:15px;">●</span> '
                    f'<span style="color:{theme.MUTED}; font-size:12px;">{meta.label if meta else metric}</span> '
                    f'<b style="color:{theme.INK};">{_fmt(self._unit, points[-1][1])}</b>'
                )
            self._chips.setText("　".join(chips))
            self._chips.show()
            self._current.hide()
            self._stats.setText("")

        # 坐标范围：使用率固定 0~100，其余从 0 起自适应
        self._plot.setXRange(start_ms / 1000, end_ms / 1000, padding=0.01)
        if self._unit == "%":
            self._plot.setYRange(0, 100, padding=0.02)
        else:
            self._plot.setYRange(0, max(peak_all, 1) * 1.15, padding=0)

    # ---- 悬浮读数 ----

    def _on_mouse_moved(self, pos) -> None:
        vb = self._plot.getPlotItem().vb
        if not self._plot.getPlotItem().sceneBoundingRect().contains(pos):
            self._vline.hide()
            self._hover.setText("")
            return
        x = vb.mapSceneToView(pos).x()
        parts = []
        for metric in self._metrics:
            points = self._series.get(metric) or []
            if not points:
                continue
            xs = [ts / 1000 for ts, _ in points]
            i = min(max(bisect_left(xs, x), 0), len(points) - 1)
            parts.append(_fmt(self._unit, points[i][1]))
        if not parts:
            return
        self._vline.setPos(x)
        self._vline.show()
        stamp = datetime.fromtimestamp(x).strftime("%m-%d %H:%M")
        self._hover.setText(f"{stamp} ・ " + " / ".join(parts))


class DetailPage(QWidget):
    def __init__(self, storage: Storage):
        super().__init__()
        self.setObjectName("page")
        self._storage = storage
        self._range_s = 3600

        pg.setConfigOptions(antialias=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        bar = QHBoxLayout()
        instance_label = QLabel("实例")
        instance_label.setProperty("class", "hint")
        bar.addWidget(instance_label)
        self._combo = QComboBox()
        self._combo.setMinimumWidth(280)
        self._combo.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self._combo)
        bar.addStretch()

        self._range_group = QButtonGroup(self)
        for label, seconds in _RANGES:
            btn = QPushButton(label)
            btn.setProperty("rangeBtn", "true")
            btn.setCheckable(True)
            btn.setChecked(seconds == self._range_s)
            btn.clicked.connect(lambda _, s=seconds: self._set_range(s))
            self._range_group.addButton(btn)
            bar.addWidget(btn)
        layout.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        self._panels_layout = QVBoxLayout(body)
        self._panels_layout.setSpacing(12)
        self._panels_layout.setContentsMargins(0, 4, 8, 4)
        self._panels: list[MetricPanel] = []
        for title, unit, metric_names in _PANELS:
            panel = MetricPanel(title, unit, metric_names)
            self._panels.append(panel)
            self._panels_layout.addWidget(panel)
        self._panels_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll)

        self._empty = QLabel("暂无数据")
        self._empty.setProperty("class", "hint")
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
        all_metrics = [m for _, _, group in _PANELS for m in group]
        series = self._storage.query_range(iid, all_metrics, start_ms, end_ms)
        self._empty.setVisible(not any(series.values()))
        for panel in self._panels:
            panel.update_data(series, start_ms, end_ms)
