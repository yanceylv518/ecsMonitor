"""真实数据源：阿里云云监控 DescribeMetricList + ECS DescribeInstances。

阶段 2 实现。接口契约见 source.MetricSource。
"""
from __future__ import annotations

from .models import DataPoint, InstanceInfo
from .source import MetricSource, SourceError


class AliyunMetricSource(MetricSource):
    """凭证与地域由构造参数注入；SDK 客户端惰性创建。"""

    def __init__(self, region_id: str, access_key_id: str, access_key_secret: str):
        self._region_id = region_id
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret

    def list_instances(self) -> list[InstanceInfo]:
        raise SourceError("真实数据源尚未实现（开发阶段 2），请先使用 --mock 模式运行")

    def fetch_metrics(
        self,
        instance_ids: list[str],
        metric_names: list[str],
        start_ms: int,
        end_ms: int,
    ) -> list[DataPoint]:
        raise SourceError("真实数据源尚未实现（开发阶段 2），请先使用 --mock 模式运行")
