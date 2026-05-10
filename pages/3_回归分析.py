import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import io
from utils.db import load_data, table_exists
from utils.stats import run_panel_regression, run_pooled_ols

st.set_page_config(page_title="回归分析", page_icon="📈", layout="wide")
st.title("📈 回归分析")
st.caption("双向固定效应面板回归 | 聚类稳健标准误")

if not table_exists("panel_dataset"):
    st.warning("请先完成数据采集并构建面板数据集。")
    st.stop()

panel = load_data("panel_dataset")
if panel.empty:
    st.warning("数据集为空。")
    st.stop()

numeric_cols = panel.select_dtypes(include="number").columns.tolist()
exclude = ["year"]
numeric_cols = [c for c in numeric_cols if c not in exclude]

VAR_LABELS = {
    "resource_rents":    "总资源租金 (% GDP)",
    "oil_rents":         "石油租金 (% GDP)",
    "gas_rents":         "天然气租金 (% GDP)",
    "coal_rents":        "煤炭租金 (% GDP)",
    "mineral_rents":     "矿产租金 (% GDP)",
    "pm25":              "PM2.5 (μg/m³)",
    "co2_pc":            "CO2排放 (人均吨)",
    "airpol_mortality":  "大气污染死亡率",
    "death_rate":        "粗死亡率",
    "ln_gdp_pc":         "ln(人均GDP-PPP)",
    "gdp_pc_ppp":        "人均GDP-PPP",
    "urbanization":      "城镇化率 (%)",
    "trade_gdp":         "贸易开放度 (%)",
    "corruption_control":"腐败控制指数",
    "govt_effectiveness":"政府效能指数",
    "manufacturing_share":"制造业占比 (%)",
    "renewable_energy":  "可再生能源占比 (%)",
    "energy_use":        "能源消耗",
    "coal_electricity":  "煤电占比 (%)",
}

def fmt(v):
    return VAR_LABELS.get(v, v)

# ── 变量选择 ──────────────────────────────────────────────────────────────────
st.subheader("变量设置")
col1, col2 = st.columns(2)

with col1:
    y_var = st.selectbox(
        "因变量 (Y)",
        options=numeric_cols,
        index=numeric_cols.index("pm25") if "pm25" in numeric_cols else 0,
        format_func=fmt,
    )

    default_x = [v for v in ["resource_rents"] if v in numeric_cols]
    x_vars = st.multiselect(
        "核心自变量（资源依赖指标）",
        options=[v for v in numeric_cols if v != y_var],
        default=default_x,
        format_func=fmt,
    )

    default_ctrl = [v for v in ["ln_gdp_pc","urbanization","trade_gdp","renewable_energy"]
                    if v in numeric_cols]
    control_vars = st.multiselect(
        "控制变量",
        options=[v for v in numeric_cols if v != y_var and v not in x_vars],
        default=default_ctrl,
        format_func=fmt,
    )

with col2:
    st.markdown("**固定效应设置**")
    entity_fe = st.checkbox("国家固定效应", value=True)
    time_fe   = st.checkbox("时间固定效应", value=True)
    cluster   = st.checkbox("聚类标准误（按国家）", value=True)

    st.markdown("**样本筛选**")
    if "year" in panel.columns:
        years = sorted(panel["year"].dropna().unique().astype(int))
        year_range = st.slider("年份范围", min_value=years[0], max_value=years[-1],
                               value=(years[0], years[-1]))
        panel_sub = panel[(panel["year"] >= year_range[0]) & (panel["year"] <= year_range[1])]
    else:
        panel_sub = panel

    if "income_level" in panel.columns:
        income_opts = ["全部"] + sorted(panel["income_level"].dropna().unique().tolist())
        income_filter = st.selectbox("收入组筛选", income_opts)
        if income_filter != "全部":
            panel_sub = panel_sub[panel_sub["income_level"] == income_filter]

    if "region" in panel.columns:
        region_opts = ["全部"] + sorted(panel["region"].dropna().unique().tolist())
        region_filter = st.selectbox("地区筛选", region_opts)
        if region_filter != "全部":
            panel_sub = panel_sub[panel_sub["region"] == region_filter]

st.divider()

# ── 运行回归 ──────────────────────────────────────────────────────────────────
all_x = x_vars + control_vars

if st.button("运行回归", type="primary", disabled=len(all_x) == 0):
    if not all_x:
        st.warning("请至少选择一个自变量。")
    else:
        with st.spinner("正在计算…"):
            result = run_panel_regression(
                panel_sub, y_var, all_x,
                entity_effects=entity_fe,
                time_effects=time_fe,
                cluster_entity=cluster,
            )
        st.session_state["reg_result"] = result
        st.session_state["reg_y"]      = y_var
        st.session_state["reg_x"]      = all_x

# ── 显示结果 ──────────────────────────────────────────────────────────────────
if "reg_result" in st.session_state:
    result = st.session_state["reg_result"]

    if "error" in result:
        st.error(f"回归失败：{result['error']}")
    else:
        st.subheader("回归结果")

        # Stats bar
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("观测值", f"{result['n_obs']:,}")
        c2.metric("国家数", f"{result['n_entities']:,}")
        c3.metric("组内R²", f"{result['r2_within']:.4f}")
        c4.metric("国家FE", "✅" if result["entity_effects"] else "❌")
        c5.metric("时间FE", "✅" if result["time_effects"] else "❌")

        # Coefficient table
        tbl = result["table"].copy()
        tbl["变量"] = tbl["变量"].apply(fmt)
        st.dataframe(tbl.style.apply(
            lambda row: ["font-weight: bold" if row["p值"] < 0.05 else "" for _ in row],
            axis=1
        ), use_container_width=True, hide_index=True)
        st.caption("*** p<0.01   ** p<0.05   * p<0.1")

        # Coefficient plot
        plot_df = result["table"][result["table"]["变量"] != "const"].copy()
        plot_df["变量标签"] = plot_df["变量"].apply(fmt)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["系数"], y=plot_df["变量标签"],
            mode="markers",
            marker=dict(size=10, color=["red" if p < 0.05 else "gray"
                                         for p in plot_df["p值"]]),
            error_x=dict(type="data", array=1.96 * plot_df["标准误"].values, visible=True),
            name="系数 ± 1.96×SE",
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="black")
        fig.update_layout(title="回归系数图（红色 = p<0.05）",
                          xaxis_title="系数", height=max(300, len(plot_df) * 50 + 100))
        st.plotly_chart(fig, use_container_width=True)

        # Export
        col1, col2 = st.columns(2)
        with col1:
            csv = tbl.to_csv(index=False).encode("utf-8-sig")
            st.download_button("导出结果表 (CSV)", data=csv,
                               file_name="regression_result.csv", mime="text/csv")
        with col2:
            txt = result["summary_str"].encode("utf-8")
            st.download_button("导出完整摘要 (TXT)", data=txt,
                               file_name="regression_summary.txt", mime="text/plain")

        # Robustness: show Pooled OLS side by side
        with st.expander("稳健性对比：Pooled OLS（无固定效应）"):
            res_pooled = run_pooled_ols(panel_sub, st.session_state["reg_y"],
                                        st.session_state["reg_x"])
            if "error" in res_pooled:
                st.error(res_pooled["error"])
            else:
                res_pooled["table"]["变量"] = res_pooled["table"]["变量"].apply(fmt)
                st.dataframe(res_pooled["table"], use_container_width=True, hide_index=True)
