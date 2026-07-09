import pytest

from ecs_monitor.core.config import AppConfig


def test_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = AppConfig(region_id="cn-beijing", interval_seconds=30, instance_ids=["i-x"])
    cfg.save(p)
    loaded = AppConfig.load(p)
    assert loaded == cfg


def test_load_missing_file_uses_defaults(tmp_path):
    cfg = AppConfig.load(tmp_path / "nope.json")
    assert cfg.region_id == "cn-hangzhou"
    assert cfg.metrics  # 默认指标非空


def test_load_ignores_unknown_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"region_id": "cn-shanghai", "legacy_field": 1}', encoding="utf-8")
    cfg = AppConfig.load(p)
    assert cfg.region_id == "cn-shanghai"


def test_validate_rejects_bad_interval():
    with pytest.raises(ValueError):
        AppConfig(interval_seconds=1).validate()
