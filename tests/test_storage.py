import time

from ecs_monitor.core.models import DataPoint, InstanceInfo
from ecs_monitor.core.storage import Storage


def make_storage(tmp_path):
    return Storage(tmp_path / "test.db")


def dp(iid="i-a", metric="CPUUtilization", ts=1000, avg=50.0):
    return DataPoint(iid, metric, ts, avg, avg + 5, avg - 5)


def test_insert_and_dedupe(tmp_path):
    s = make_storage(tmp_path)
    points = [dp(ts=1000), dp(ts=2000), dp(ts=3000)]
    assert s.insert_datapoints(points) == 3
    # 重复写入被唯一索引去重
    assert s.insert_datapoints(points) == 0
    assert s.datapoint_count() == 3


def test_upsert_instances(tmp_path):
    s = make_storage(tmp_path)
    s.upsert_instances([InstanceInfo("i-a", "web-01", "cn-hangzhou", "Running")])
    s.upsert_instances([InstanceInfo("i-a", "web-01", "cn-hangzhou", "Stopped")])
    instances = s.list_instances()
    assert len(instances) == 1
    assert instances[0].status == "Stopped"


def test_latest_values(tmp_path):
    s = make_storage(tmp_path)
    s.insert_datapoints([
        dp(ts=1000, avg=10),
        dp(ts=3000, avg=30),
        dp(ts=2000, avg=20),
        dp(iid="i-b", ts=5000, avg=99),
    ])
    latest = s.latest_values()
    assert latest["i-a"]["CPUUtilization"] == (3000, 30)
    assert latest["i-b"]["CPUUtilization"] == (5000, 99)


def test_query_range(tmp_path):
    s = make_storage(tmp_path)
    s.insert_datapoints([dp(ts=t, avg=t / 100) for t in range(1000, 10001, 1000)])
    series = s.query_range("i-a", ["CPUUtilization"], 3000, 7000)
    assert [ts for ts, _ in series["CPUUtilization"]] == [3000, 4000, 5000, 6000, 7000]
    # 未命中的指标返回空列表而非缺 key
    series = s.query_range("i-a", ["memory_usedutilization"], 0, 99999)
    assert series["memory_usedutilization"] == []


def test_purge(tmp_path):
    s = make_storage(tmp_path)
    now_ms = int(time.time() * 1000)
    old_ms = now_ms - 40 * 86400 * 1000
    s.insert_datapoints([dp(ts=old_ms), dp(ts=now_ms)])
    assert s.purge_older_than(30) == 1
    assert s.datapoint_count() == 1
    assert s.purge_older_than(0) == 0  # 0 = 永久保留，不清理
