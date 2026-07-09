"""视觉主题：颜色令牌与全局样式。

色值取自经过色盲安全校验的参考调色板（dataviz 参考实例，浅色模式）。
本应用界面固定为浅色主题，保证图表颜色与底色的对比度经过验证。
"""
from __future__ import annotations

# ---- 图表分类色（固定顺序分配，不循环）----
SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300"]  # 蓝 青 黄 绿
ACCENT = SERIES[0]  # 单序列图表与选中态统一用蓝

# ---- 状态色（专用，不与序列色混用）----
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"

# ---- 界面基调 ----
PAGE_BG = "#f9f9f7"  # 页面底色
SURFACE = "#fcfcfb"  # 卡片/图表面板底色
INK = "#0b0b0b"  # 主文字
INK_2 = "#52514e"  # 次级文字
MUTED = "#898781"  # 弱化文字（轴、标签）
GRID = "#e1e0d9"  # 网格线
BORDER = "rgba(11, 11, 11, 0.10)"  # 细边框

APP_QSS = f"""
QMainWindow, QWidget#page {{
    background: {PAGE_BG};
}}
QStatusBar {{
    background: {SURFACE};
    color: {INK_2};
}}

/* ---- 侧边导航 ---- */
QListWidget#nav {{
    background: {SURFACE};
    border: none;
    border-right: 1px solid {GRID};
    font-size: 15px;
    outline: 0;
    padding-top: 8px;
}}
QListWidget#nav::item {{
    height: 46px;
    padding-left: 18px;
    border-left: 3px solid transparent;
    color: {INK_2};
}}
QListWidget#nav::item:hover {{
    background: {PAGE_BG};
}}
QListWidget#nav::item:selected {{
    background: #edf3fc;
    border-left: 3px solid {ACCENT};
    color: {INK};
}}

/* ---- 实例卡片 ---- */
QFrame#card {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {SURFACE};
}}
QFrame#card[alert="true"] {{
    border: 2px solid {CRITICAL};
}}
QFrame#card[stopped="true"] {{
    background: {PAGE_BG};
}}
QLabel#cardName {{
    font-size: 15px;
    font-weight: 600;
    color: {INK};
}}
QLabel#cardId {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel.metricLabel {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel.metricValue {{
    font-size: 16px;
    font-weight: 600;
    color: {INK};
}}
QLabel.metricValue[alert="true"] {{
    color: {CRITICAL};
}}
QLabel.metricValue[primary="true"] {{
    font-size: 20px;
}}

/* ---- 详情页指标面板 ---- */
QFrame#panel {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {SURFACE};
}}
QLabel#panelTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {INK};
}}
QLabel#panelCurrent {{
    font-size: 22px;
    font-weight: 700;
    color: {INK};
}}
QLabel.panelStat {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#hoverReadout {{
    color: {INK_2};
    font-size: 12px;
}}

/* ---- 时间范围按钮 ---- */
QPushButton[rangeBtn="true"] {{
    padding: 5px 14px;
    border: 1px solid {GRID};
    border-radius: 6px;
    background: {SURFACE};
    color: {INK_2};
}}
QPushButton[rangeBtn="true"]:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}

/* ---- 通用弱化提示 ---- */
QLabel.hint {{
    color: {MUTED};
    font-size: 12px;
}}
"""
