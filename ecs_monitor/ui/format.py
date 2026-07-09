"""UI 数值格式化工具。"""
from __future__ import annotations

import time


def format_rate(bps: float) -> str:
    """带宽/吞吐人性化显示（输入 bps 或 Bps，单位跟随语义由调用方保证）。"""
    for unit in ("", "K", "M", "G", "T"):
        if abs(bps) < 1000:
            return f"{bps:.1f} {unit}bps" if unit else f"{bps:.0f} bps"
        bps /= 1000
    return f"{bps:.1f} Pbps"


def format_bytes_rate(value: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB/s"


def format_time_ago(epoch_s: float) -> str:
    delta = int(time.time() - epoch_s)
    if delta < 5:
        return "刚刚"
    if delta < 60:
        return f"{delta} 秒前"
    if delta < 3600:
        return f"{delta // 60} 分钟前"
    return time.strftime("%H:%M:%S", time.localtime(epoch_s))
