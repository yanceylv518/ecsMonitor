"""设置页：凭证、采集参数、指标勾选；保存后热更新采集线程。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core import credentials
from ..core.config import AppConfig
from ..core.models import METRICS
from ..core.source import MetricSource, SourceError

# 组装层注入：根据 (config, secret) 构造数据源（mock / 真实的差异收敛在 main.py）
SourceFactory = Callable[[AppConfig, str], MetricSource]

_REGIONS = [
    "cn-hangzhou", "cn-shanghai", "cn-beijing", "cn-shenzhen", "cn-qingdao",
    "cn-zhangjiakou", "cn-chengdu", "cn-hongkong", "ap-southeast-1", "us-west-1",
]


class _ConnectionTester(QThread):
    """后台执行 test_connection，避免阻塞 UI。"""

    finished_ok = Signal(int)
    failed = Signal(str)

    def __init__(self, source: MetricSource):
        super().__init__()
        self._source = source

    def run(self) -> None:
        try:
            self.finished_ok.emit(self._source.test_connection())
        except SourceError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"未知错误: {e}")


class SettingsPage(QWidget):
    config_saved = Signal(AppConfig)

    def __init__(self, config: AppConfig, source_factory: SourceFactory):
        super().__init__()
        self._source_factory = source_factory
        self._tester: _ConnectionTester | None = None

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        # --- 凭证 ---
        cred_box = QGroupBox("阿里云凭证（建议使用只读 RAM 子账号）")
        cred_form = QFormLayout(cred_box)
        self._region = QComboBox()
        self._region.addItems(_REGIONS)
        self._region.setEditable(True)
        self._ak_id = QLineEdit()
        self._ak_id.setPlaceholderText("LTAI...")
        self._ak_secret = QLineEdit()
        self._ak_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._ak_secret.setPlaceholderText("保存后存入系统凭据管理器，不落明文")
        cred_form.addRow("地域:", self._region)
        cred_form.addRow("AccessKey ID:", self._ak_id)
        cred_form.addRow("AccessKey Secret:", self._ak_secret)
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("测试连接")
        self._test_btn.clicked.connect(self._test_connection)
        self._test_result = QLabel("")
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_result, stretch=1)
        cred_form.addRow(test_row)
        layout.addWidget(cred_box)

        # --- 采集参数 ---
        col_box = QGroupBox("采集")
        col_form = QFormLayout(col_box)
        self._interval = QSpinBox()
        self._interval.setRange(10, 3600)
        self._interval.setSuffix(" 秒")
        self._retention = QSpinBox()
        self._retention.setRange(0, 3650)
        self._retention.setSuffix(" 天（0 = 永久）")
        self._instances_edit = QPlainTextEdit()
        self._instances_edit.setPlaceholderText("每行一个实例 ID；留空 = 自动发现该地域全部实例")
        self._instances_edit.setMaximumHeight(80)
        col_form.addRow("采集间隔:", self._interval)
        col_form.addRow("数据保留:", self._retention)
        col_form.addRow("指定实例:", self._instances_edit)
        layout.addWidget(col_box)

        # --- 指标勾选 ---
        metric_box = QGroupBox("采集指标")
        metric_grid = QGridLayout(metric_box)
        self._metric_checks: dict[str, QCheckBox] = {}
        for idx, meta in enumerate(METRICS.values()):
            text = meta.label + (" *" if meta.needs_agent else "")
            check = QCheckBox(text)
            check.setToolTip(meta.name + ("（需实例安装云监控插件）" if meta.needs_agent else ""))
            self._metric_checks[meta.name] = check
            metric_grid.addWidget(check, idx // 3, idx % 3)
        metric_grid.addWidget(QLabel("* 需实例安装云监控插件"), (len(METRICS) // 3) + 1, 0, 1, 3)
        layout.addWidget(metric_box)

        # --- 告警阈值 ---
        alert_box = QGroupBox("告警阈值（总览卡片标红）")
        alert_form = QFormLayout(alert_box)
        self._cpu_threshold = QDoubleSpinBox()
        self._cpu_threshold.setRange(1, 100)
        self._cpu_threshold.setSuffix(" %")
        self._mem_threshold = QDoubleSpinBox()
        self._mem_threshold.setRange(1, 100)
        self._mem_threshold.setSuffix(" %")
        alert_form.addRow("CPU:", self._cpu_threshold)
        alert_form.addRow("内存:", self._mem_threshold)
        layout.addWidget(alert_box)

        # --- 保存 ---
        save_row = QHBoxLayout()
        self._save_btn = QPushButton("保存并应用")
        self._save_btn.clicked.connect(self._save)
        self._save_result = QLabel("")
        save_row.addWidget(self._save_btn)
        save_row.addWidget(self._save_result, stretch=1)
        layout.addLayout(save_row)
        layout.addStretch()

        self._load(config)

    # ---- 表单读写 ----

    def _load(self, cfg: AppConfig) -> None:
        self._region.setCurrentText(cfg.region_id)
        self._ak_id.setText(cfg.access_key_id)
        secret = credentials.get_secret(cfg.access_key_id) if cfg.access_key_id else None
        if secret:
            self._ak_secret.setText(secret)
        self._interval.setValue(cfg.interval_seconds)
        self._retention.setValue(cfg.retention_days)
        self._instances_edit.setPlainText("\n".join(cfg.instance_ids))
        for name, check in self._metric_checks.items():
            check.setChecked(name in cfg.metrics)
        self._cpu_threshold.setValue(cfg.cpu_alert_threshold)
        self._mem_threshold.setValue(cfg.mem_alert_threshold)

    def _collect_form(self) -> AppConfig:
        cfg = AppConfig.load()  # 以磁盘配置为基底，避免覆盖未在表单中的字段
        cfg.region_id = self._region.currentText().strip()
        cfg.access_key_id = self._ak_id.text().strip()
        cfg.interval_seconds = self._interval.value()
        cfg.retention_days = self._retention.value()
        cfg.instance_ids = [
            line.strip() for line in self._instances_edit.toPlainText().splitlines() if line.strip()
        ]
        cfg.metrics = [name for name, check in self._metric_checks.items() if check.isChecked()]
        cfg.cpu_alert_threshold = self._cpu_threshold.value()
        cfg.mem_alert_threshold = self._mem_threshold.value()
        return cfg

    # ---- 动作 ----

    def _test_connection(self) -> None:
        try:
            cfg = self._collect_form()
        except ValueError as e:
            self._test_result.setText(f"❌ {e}")
            return
        self._test_btn.setEnabled(False)
        self._test_result.setText("连接中…")
        self._tester = _ConnectionTester(self._source_factory(cfg, self._ak_secret.text()))
        self._tester.finished_ok.connect(self._on_test_ok)
        self._tester.failed.connect(self._on_test_failed)
        self._tester.start()

    def _on_test_ok(self, count: int) -> None:
        self._test_btn.setEnabled(True)
        self._test_result.setText(f"✅ 连接成功，可见 {count} 个实例")

    def _on_test_failed(self, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_result.setText(f"❌ {message}")

    def _save(self) -> None:
        try:
            cfg = self._collect_form()
            cfg.validate()
        except ValueError as e:
            self._save_result.setText(f"❌ {e}")
            return
        secret = self._ak_secret.text()
        if cfg.access_key_id and secret:
            persisted = credentials.set_secret(cfg.access_key_id, secret)
            if not persisted:
                self._save_result.setText("⚠️ 已保存；但系统凭据管理器不可用，Secret 仅本次运行有效")
        cfg.save()
        self.config_saved.emit(cfg)
        if not self._save_result.text().startswith("⚠️"):
            self._save_result.setText("✅ 已保存并应用")
