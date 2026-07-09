"""核心数据模型：与 GUI 无关，禁止 import Qt。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstanceInfo:
    """ECS 实例元信息。"""

    instance_id: str
    instance_name: str
    region_id: str
    status: str  # Running / Stopped / Starting / Stopping


@dataclass(frozen=True)
class DataPoint:
    """一个监控数据点（对应云监控 Datapoints 中的一条）。"""

    instance_id: str
    metric_name: str
    timestamp: int  # UTC 毫秒时间戳
    average: float | None = None
    maximum: float | None = None
    minimum: float | None = None


@dataclass(frozen=True)
class MetricMeta:
    """指标的静态元信息，用于 UI 展示与分组。"""

    name: str  # 云监控指标名
    label: str  # 界面显示名
    unit: str  # %, bps, Bps
    group: str  # cpu_mem / network / disk
    needs_agent: bool = False  # 是否需要实例安装云监控插件


# 支持的全部指标（设置页勾选范围）
METRICS: dict[str, MetricMeta] = {
    m.name: m
    for m in [
        MetricMeta("CPUUtilization", "CPU使用率", "%", "cpu_mem"),
        MetricMeta("memory_usedutilization", "内存使用率", "%", "cpu_mem", needs_agent=True),
        MetricMeta("diskusage_utilization", "磁盘使用率", "%", "disk", needs_agent=True),
        MetricMeta("InternetInRate", "公网入带宽", "bps", "network"),
        MetricMeta("InternetOutRate", "公网出带宽", "bps", "network"),
        MetricMeta("IntranetInRate", "内网入带宽", "bps", "network"),
        MetricMeta("IntranetOutRate", "内网出带宽", "bps", "network"),
        MetricMeta("DiskReadBPS", "磁盘读吞吐", "Bps", "disk"),
        MetricMeta("DiskWriteBPS", "磁盘写吞吐", "Bps", "disk"),
    ]
}

DEFAULT_METRICS = [
    "CPUUtilization",
    "memory_usedutilization",
    "diskusage_utilization",
    "InternetInRate",
    "InternetOutRate",
    "DiskReadBPS",
    "DiskWriteBPS",
]
