import streamlit as st
import pandas as pd
from utils.collector import (
    INDICATOR_GROUPS, fetch_world_bank, fetch_country_metadata,
    fetch_who_mortality, build_panel_dataset,
)
from utils.db import load_data, table_exists, get_db_summary

st.set_page_config(page_title="数据采集", page_icon="📥", layout="wide")
st.title("📥 数据采集")
st.caption("从世界银行API和WHO GHO自动获取全球面板数据")

# ── Step 1: 国家元数据 ────────────────────────────────────────────────────────
st.subheader("Step 1 — 国家元数据")
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("获取各国的收入分组、地区分类信息（国家名称/地区/收入水平），用于后续异质性分析。")
with col2:
    if st.button("获取国家元数据", type="primary", use_container_width=True):
        with st.spinner("正在获取…"):
            df_meta = fetch_country_metadata()
        st.success(f"完成，共 {len(df_meta)} 个经济体。")

if table_exists("country_metadata"):
    df_meta = load_data("country_metadata")
    if not df_meta.empty:
        with st.expander("预览元数据"):
            st.dataframe(df_meta.head(20), use_container_width=True, hide_index=True)
        cols = st.columns(4)
        cols[0].metric("经济体总数", len(df_meta))
        cols[1].metric("地区数", df_meta["region"].nunique())
        cols[2].metric("收入组数", df_meta["income_level"].nunique())

st.divider()

# ── Step 2: 世界银行指标数据 ──────────────────────────────────────────────────
st.subheader("Step 2 — 世界银行指标数据")

col_left, col_right = st.columns([2, 1])
with col_left:
    selected_groups = st.multiselect(
        "选择要采集的指标组（建议全选）",
        options=list(INDICATOR_GROUPS.keys()),
        default=list(INDICATOR_GROUPS.keys()),
    )
    for grp in selected_groups:
        with st.expander(f"📋 {grp} — 包含指标"):
            for code, name in INDICATOR_GROUPS[grp].items():
                st.markdown(f"- `{code}` {name}")

with col_right:
    start_year = st.number_input("起始年份", min_value=1990, max_value=2020, value=2003)
    end_year   = st.number_input("结束年份", min_value=2000, max_value=2024, value=2022)
    st.markdown("")
    fetch_wb = st.button("开始采集世界银行数据", type="primary", use_container_width=True,
                         disabled=len(selected_groups) == 0)

if fetch_wb:
    if not selected_groups:
        st.warning("请至少选择一个指标组。")
    else:
        st.info(f"正在从世界银行API获取数据，约需 2–5 分钟，请勿关闭页面…")
        prog = st.progress(0)
        status = st.empty()
        n = fetch_world_bank(selected_groups, int(start_year), int(end_year),
                             progress_bar=prog, status_text=status)
        status.empty()
        prog.progress(1.0)
        st.success(f"采集完成！共获取 {n:,} 条记录。")

if table_exists("raw_wb_data"):
    raw = load_data("raw_wb_data")
    if not raw.empty:
        st.markdown("**已有世界银行数据概览**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("记录总数", f"{len(raw):,}")
        c2.metric("国家数", raw["country_code"].nunique())
        c3.metric("指标数", raw["indicator_code"].nunique())
        c4.metric("年份范围", f"{int(raw['year'].min())}–{int(raw['year'].max())}")

        with st.expander("查看各指标覆盖情况"):
            coverage = (
                raw.groupby("indicator_code")
                .agg(国家数=("country_code", "nunique"),
                     记录数=("value", "count"),
                     起始年=("year", "min"),
                     结束年=("year", "max"))
                .reset_index()
            )
            name_map = {}
            for grp in INDICATOR_GROUPS.values():
                name_map.update(grp)
            coverage.insert(1, "指标名称", coverage["indicator_code"].map(name_map))
            st.dataframe(coverage, use_container_width=True, hide_index=True)

st.divider()

# ── Step 3: WHO 死亡数据 ──────────────────────────────────────────────────────
st.subheader("Step 3 — WHO 大气污染死亡数据（可选）")
st.markdown("补充获取 WHO GHO 的室外/室内空气污染死亡率（世界银行数据已包含基础死亡率指标）。")

col1, col2 = st.columns([3, 1])
with col2:
    fetch_who = st.button("获取 WHO 数据", use_container_width=True)

if fetch_who:
    prog2 = st.progress(0)
    status2 = st.empty()
    n2 = fetch_who_mortality(progress_bar=prog2, status_text=status2)
    status2.empty()
    if n2 > 0:
        st.success(f"WHO数据采集完成，共 {n2:,} 条记录。")
    else:
        st.warning("WHO数据获取失败，可能是网络问题，世界银行数据已足够分析。")

st.divider()

# ── Step 4: 构建面板数据集 ────────────────────────────────────────────────────
st.subheader("Step 4 — 构建合并面板数据集")
st.markdown("将所有指标合并为宽格式面板数据（国家 × 年份），用于回归分析。")

col1, col2 = st.columns([3, 1])
with col2:
    build_btn = st.button("构建面板数据集", type="primary", use_container_width=True,
                          disabled=not table_exists("raw_wb_data"))

if build_btn:
    with st.spinner("正在合并数据…"):
        panel = build_panel_dataset()
    if not panel.empty:
        st.success(f"面板数据集构建完成！共 {len(panel):,} 个国家-年份观测值。")
    else:
        st.error("构建失败，请先完成世界银行数据采集。")

if table_exists("panel_dataset"):
    panel = load_data("panel_dataset")
    if not panel.empty:
        st.markdown("**面板数据集预览**")
        c1, c2, c3 = st.columns(3)
        c1.metric("观测值", f"{len(panel):,}")
        c2.metric("国家数", panel["country_code"].nunique())
        c3.metric("年份范围", f"{int(panel['year'].min())}–{int(panel['year'].max())}")

        with st.expander("查看数据（前50行）"):
            st.dataframe(panel.head(50), use_container_width=True, hide_index=True)

        # 缺失值热力图
        with st.expander("各变量覆盖率"):
            numeric_cols = panel.select_dtypes(include="number").columns.tolist()
            coverage_df = pd.DataFrame({
                "变量": numeric_cols,
                "有效观测": [panel[c].notna().sum() for c in numeric_cols],
                "覆盖率(%)": [(panel[c].notna().sum() / len(panel) * 100).round(1) for c in numeric_cols],
            }).sort_values("覆盖率(%)", ascending=False)
            st.dataframe(coverage_df, use_container_width=True, hide_index=True)

        # 导出按钮
        csv = panel.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "导出面板数据集 (CSV)",
            data=csv,
            file_name="panel_dataset.csv",
            mime="text/csv",
        )
