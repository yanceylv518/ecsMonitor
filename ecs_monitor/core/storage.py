"""SQLite 存储层。

线程约定：SQLite 连接不跨线程共享 —— 采集线程与 UI 线程各自创建 Storage 实例。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .models import DataPoint, InstanceInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    average     REAL,
    maximum     REAL,
    minimum     REAL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_metrics
    ON metrics(instance_id, metric_name, timestamp);
CREATE INDEX IF NOT EXISTS ix_metrics_query
    ON metrics(instance_id, metric_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS instances (
    instance_id   TEXT PRIMARY KEY,
    instance_name TEXT,
    region_id     TEXT,
    status        TEXT,
    updated_at    TEXT
);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- 写入（采集线程） ----

    def upsert_instances(self, instances: list[InstanceInfo]) -> None:
        self._conn.executemany(
            """INSERT INTO instances(instance_id, instance_name, region_id, status, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(instance_id) DO UPDATE SET
                 instance_name=excluded.instance_name,
                 region_id=excluded.region_id,
                 status=excluded.status,
                 updated_at=excluded.updated_at""",
            [(i.instance_id, i.instance_name, i.region_id, i.status) for i in instances],
        )
        self._conn.commit()

    def insert_datapoints(self, points: list[DataPoint]) -> int:
        """批量写入，唯一索引去重。返回实际新增条数。"""
        cur = self._conn.executemany(
            """INSERT OR IGNORE INTO metrics
               (instance_id, metric_name, timestamp, average, maximum, minimum)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (p.instance_id, p.metric_name, p.timestamp, p.average, p.maximum, p.minimum)
                for p in points
            ],
        )
        self._conn.commit()
        return cur.rowcount if cur.rowcount != -1 else 0

    def purge_older_than(self, days: int) -> int:
        """删除超过保留期的数据点，返回删除条数。days<=0 不清理。"""
        if days <= 0:
            return 0
        cutoff_ms = int((time.time() - days * 86400) * 1000)
        cur = self._conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff_ms,))
        self._conn.commit()
        return cur.rowcount

    # ---- 查询（UI 线程） ----

    def list_instances(self) -> list[InstanceInfo]:
        rows = self._conn.execute(
            "SELECT instance_id, instance_name, region_id, status FROM instances ORDER BY instance_name"
        ).fetchall()
        return [InstanceInfo(*r) for r in rows]

    def latest_values(self) -> dict[str, dict[str, tuple[int, float]]]:
        """每个实例每个指标的最新数据点：{instance_id: {metric: (timestamp, average)}}"""
        rows = self._conn.execute(
            """SELECT m.instance_id, m.metric_name, m.timestamp, m.average
               FROM metrics m
               JOIN (SELECT instance_id, metric_name, MAX(timestamp) AS ts
                     FROM metrics GROUP BY instance_id, metric_name) t
                 ON m.instance_id = t.instance_id
                AND m.metric_name = t.metric_name
                AND m.timestamp = t.ts"""
        ).fetchall()
        out: dict[str, dict[str, tuple[int, float]]] = {}
        for iid, metric, ts, avg in rows:
            out.setdefault(iid, {})[metric] = (ts, avg)
        return out

    def query_range(
        self, instance_id: str, metric_names: list[str], start_ms: int, end_ms: int
    ) -> dict[str, list[tuple[int, float]]]:
        """查询单实例多指标的时间序列：{metric: [(timestamp, average), ...]} 按时间升序。"""
        out: dict[str, list[tuple[int, float]]] = {m: [] for m in metric_names}
        if not metric_names:
            return out
        placeholders = ",".join("?" * len(metric_names))
        rows = self._conn.execute(
            f"""SELECT metric_name, timestamp, average FROM metrics
                WHERE instance_id = ? AND metric_name IN ({placeholders})
                  AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp""",
            [instance_id, *metric_names, start_ms, end_ms],
        ).fetchall()
        for metric, ts, avg in rows:
            if avg is not None:
                out[metric].append((ts, avg))
        return out

    def datapoint_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
