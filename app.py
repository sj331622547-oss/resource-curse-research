import streamlit as st
from utils.db import get_db_summary, get_collection_log, table_exists

st.set_page_config(
    page_title="资源诅咒与大气环境研究平台",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 资源诅咒与大气环境研究平台")
st.caption("Nature Communications 论文数据支持系统 | 全球面板数据 2003–2022")

st.divider()

# ── 研究框架说明 ──────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("研究框架")
    st.markdown("""
    **核心假说：** 自然资源依赖 → 大气环境恶化 → 健康损害（死亡率上升）

    **传导机制：**
    - 路径①：资源依赖 → 腐败/制度弱化 → 环境监管失灵 → 大气污染
    - 路径②：资源依赖 → 产业结构重工业化 → 排放增加 → 大气污染
    - 路径③：资源依赖 → 化石燃料补贴 → 能源结构扭曲 → 大气污染

    **识别策略：** 双向固定效应面板回归（国家FE + 时间FE）+ 聚类稳健标准误
    """)

with col2:
    st.subheader("数据库状态")
    summary = get_db_summary()
    if not summary:
        st.info("数据库为空，请前往「数据采集」页面获取数据。")
    else:
        labels = {
            "raw_wb_data":      "世界银行原始数据",
            "raw_who_data":     "WHO死亡数据",
            "country_metadata": "国家元数据",
            "panel_dataset":    "面板数据集",
            "collection_log":   "采集日志",
        }
        for tbl, cnt in summary.items():
            name = labels.get(tbl, tbl)
            st.metric(name, f"{cnt:,} 行")

st.divider()

# ── 快速导航 ──────────────────────────────────────────────────────────────────
st.subheader("功能导航")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("### 📥 数据采集\n从世界银行、WHO自动拉取数据，构建面板数据集。\n\n👉 **侧边栏 → 数据采集**")
with c2:
    st.markdown("### 📊 数据看板\n交互式世界地图、趋势图、散点图、描述统计。\n\n👉 **侧边栏 → 数据看板**")
with c3:
    st.markdown("### 📈 回归分析\n双向固定效应面板回归，可导出论文格式结果表。\n\n👉 **侧边栏 → 回归分析**")
with c4:
    st.markdown("### 🔍 机制检验\n中介分析（Sobel检验）+ 异质性分组回归。\n\n👉 **侧边栏 → 机制检验**")

st.divider()

# ── 最近采集日志 ──────────────────────────────────────────────────────────────
if table_exists("collection_log"):
    log = get_collection_log()
    if not log.empty:
        st.subheader("最近采集记录")
        st.dataframe(
            log.sort_values("timestamp", ascending=False).head(10),
            use_container_width=True,
            hide_index=True,
        )
