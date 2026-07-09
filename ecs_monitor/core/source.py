"""数据源抽象接口：Mock 与真实阿里云实现均遵循此接口。

UI 与采集线程只依赖本接口，禁止出现针对具体实现的分支。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import DataPoint, InstanceInfo


class SourceError(Exception):
    """数据源调用失败（网络、鉴权、限流等），message 面向用户展示。"""


class MetricSource(ABC):
    @abstractmethod
    def list_instances(self) -> list[InstanceInfo]:
        """返回当前地域下的全部 ECS 实例元信息。失败抛 SourceError。"""

    @abstractmethod
    def fetch_metrics(
        self,
        instance_ids: list[str],
        metric_names: list[str],
        start_ms: int,
        end_ms: int,
    ) -> list[DataPoint]:
        """拉取指定实例、指标在 [start_ms, end_ms] 时间窗内的数据点。

        无数据（如实例未装插件）返回空列表，不视为错误。失败抛 SourceError。
        """

    def test_connection(self) -> int:
        """验证凭证/连通性，返回可见实例数。失败抛 SourceError。"""
        return len(self.list_instances())
