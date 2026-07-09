from ecs_monitor.core.mock_source import MockMetricSource

HOUR_MS = 3600_000


def test_list_instances():
    source = MockMetricSource()
    instances = source.list_instances()
    assert len(instances) >= 3
    statuses = {i.status for i in instances}
    assert "Running" in statuses and "Stopped" in statuses  # 覆盖 UI 的灰显状态


def test_fetch_metrics_shape():
    source = MockMetricSource()
    running = [i for i in source.list_instances() if i.status == "Running"]
    iid = running[0].instance_id
    points = source.fetch_metrics([iid], ["CPUUtilization"], 0, HOUR_MS)
    assert len(points) == 60  # 60 秒粒度，1 小时 60 个点
    for p in points:
        assert p.instance_id == iid
        assert 0 <= p.average <= 100  # 使用率指标限制在 [0, 100]
        assert p.minimum <= p.average <= p.maximum
        assert p.timestamp % 60_000 == 0  # 对齐粒度边界


def test_deterministic():
    source = MockMetricSource()
    iid = source.list_instances()[0].instance_id
    a = source.fetch_metrics([iid], ["CPUUtilization", "InternetOutRate"], 0, HOUR_MS)
    b = source.fetch_metrics([iid], ["CPUUtilization", "InternetOutRate"], 0, HOUR_MS)
    assert a == b  # 同一时间窗重复查询结果一致（增量采集数据吻合的前提）


def test_stopped_instance_has_no_data():
    source = MockMetricSource()
    stopped = [i for i in source.list_instances() if i.status == "Stopped"]
    points = source.fetch_metrics([stopped[0].instance_id], ["CPUUtilization"], 0, HOUR_MS)
    assert points == []


def test_alert_instance_high_cpu():
    source = MockMetricSource()
    points = source.fetch_metrics(["i-mock0db001"], ["CPUUtilization"], 0, 6 * HOUR_MS)
    avg = sum(p.average for p in points) / len(points)
    assert avg > 85  # 告警演示实例 CPU 持续高位
