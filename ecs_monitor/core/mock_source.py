"""Mock 数据源：生成形态逼真的仿真监控数据。

长期保留的能力（--mock 启动参数），用于 UI 开发、演示、回归与无网环境。
数据由 (实例, 指标, 时间) 确定性生成 —— 同一时间点反复查询结果一致，
因此任意历史范围（如详情页 7d 视图)都能出数，且与增量采集的数据吻合。
"""
from __future__ import annotations

import hashlib
import math

from .models import DataPoint, InstanceInfo
from .source import MetricSource

_INSTANCES = [
    InstanceInfo("i-mock0web01", "web-server-01", "cn-hangzhou", "Running"),
    InstanceInfo("i-mock0web02", "web-server-02", "cn-hangzhou", "Running"),
    InstanceInfo("i-mock0db001", "db-server-01", "cn-hangzhou", "Running"),  # 持续高 CPU（告警演示）
    InstanceInfo("i-mock0cache", "cache-server-01", "cn-hangzhou", "Running"),
    InstanceInfo("i-mock0batch", "batch-worker-01", "cn-hangzhou", "Stopped"),  # 停止态（灰显演示）
]

# 各指标的基线与波动幅度：(基线, 日间波动幅度, 噪声幅度)
_PROFILES: dict[str, tuple[float, float, float]] = {
    "CPUUtilization": (30, 25, 8),
    "memory_usedutilization": (55, 10, 3),
    "diskusage_utilization": (42, 1, 0.5),
    "InternetInRate": (2e6, 1.5e6, 8e5),
    "InternetOutRate": (5e6, 4e6, 2e6),
    "IntranetInRate": (8e6, 5e6, 3e6),
    "IntranetOutRate": (8e6, 5e6, 3e6),
    "DiskReadBPS": (3e6, 2e6, 1.5e6),
    "DiskWriteBPS": (5e6, 3e6, 2e6),
}


def _noise(instance_id: str, metric: str, bucket: int) -> float:
    """基于哈希的确定性伪随机数，范围 [-1, 1)。"""
    h = hashlib.md5(f"{instance_id}:{metric}:{bucket}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**31 - 1.0


class MockMetricSource(MetricSource):
    PERIOD_MS = 60_000  # 数据点粒度：60 秒

    def list_instances(self) -> list[InstanceInfo]:
        return list(_INSTANCES)

    def fetch_metrics(
        self,
        instance_ids: list[str],
        metric_names: list[str],
        start_ms: int,
        end_ms: int,
    ) -> list[DataPoint]:
        stopped = {i.instance_id for i in _INSTANCES if i.status != "Running"}
        points: list[DataPoint] = []
        first = (start_ms // self.PERIOD_MS + 1) * self.PERIOD_MS  # 对齐到粒度边界
        for iid in instance_ids:
            if iid in stopped:
                continue  # 停止的实例没有监控数据
            for metric in metric_names:
                profile = _PROFILES.get(metric)
                if profile is None:
                    continue
                for ts in range(first, end_ms + 1, self.PERIOD_MS):
                    avg = self._value(iid, metric, ts, profile)
                    jitter = abs(_noise(iid, metric, ts // self.PERIOD_MS + 7)) * 0.15 + 0.02
                    points.append(
                        DataPoint(
                            instance_id=iid,
                            metric_name=metric,
                            timestamp=ts,
                            average=round(avg, 3),
                            maximum=round(avg * (1 + jitter), 3),
                            minimum=round(max(avg * (1 - jitter), 0), 3),
                        )
                    )
        return points

    def _value(self, iid: str, metric: str, ts: int, profile: tuple[float, float, float]) -> float:
        base, day_amp, noise_amp = profile
        bucket = ts // self.PERIOD_MS
        day_frac = (ts % 86_400_000) / 86_400_000  # 当日进度 0~1

        # 日间波形：下午达到峰值（UTC 06:00 ≈ 北京时间 14:00）
        daily = day_amp * math.sin(2 * math.pi * (day_frac - 0.25))
        value = base + daily + noise_amp * _noise(iid, metric, bucket)

        # 实例个性
        if metric == "memory_usedutilization":
            # 内存缓慢爬升、每周回落一次（模拟周期性重启释放）
            week_frac = (ts % 604_800_000) / 604_800_000
            value = base + 25 * week_frac + noise_amp * _noise(iid, metric, bucket)
        if metric in ("InternetOutRate", "DiskWriteBPS") and _noise(iid, metric, bucket // 10) > 0.85:
            value *= 3.0  # 偶发突刺

        # 实例间基线错开，避免曲线重叠
        offset = int(hashlib.md5(iid.encode()).hexdigest()[:2], 16) / 255
        value *= 0.8 + 0.4 * offset

        # 告警演示实例：CPU 持续高位（放在基线偏移之后，避免被推到 100 钳位失真）
        if iid == "i-mock0db001" and metric == "CPUUtilization":
            value = 93 + 4 * _noise(iid, metric, bucket)

        return max(value, 0.0) if "utilization" not in metric.lower() else min(max(value, 0.0), 100.0)
