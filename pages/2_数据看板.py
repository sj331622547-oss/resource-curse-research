import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from utils.db import load_data, table_exists
from utils.stats import descriptive_stats, correlation_matrix

st.set_page_config(page_title="数据看板", page_icon="📊", layout="wide")
st.title("📊 数据看板")

if not table_exists("panel_dataset"):
    st.warning("面板数据集尚未构建，请先前往「数据采集」页面完成数据采集。")
    st.stop()

panel = load_data("panel_dataset")
if panel.empty:
    st.warning("数据集为空，请先采集数据。")
    st.stop()

# Variable labels
VAR_LABELS = {
    "resource_rents":    "总资源租金 (% GDP)",
    "oil_rents":         "石油租金 (% GDP)",
    "gas_rents":         "天然气租金 (% GDP)",
    "coal_rents":        "煤炭租金 (% GDP)",
    "mineral_rents":     "矿产租金 (% GDP)",
    "pm25":              "PM2.5 (μg/m³)",
    "co2_pc":            "CO2排放 (人均吨)",
    "airpol_mortality":  "大气污染死亡率 (per 100,000)",
    "death_rate":        "粗死亡率 (per 1,000)",
    "gdp_pc_ppp":        "人均GDP-PPP",
    "urbanization":      "城镇化率 (%)",
    "trade_gdp":         "贸易开放度 (%)",
    "corruption_control":"腐败控制指数",
    "govt_effectiveness":"政府效能指数",
    "manufacturing_share":"制造业占比 (%)",
    "renewable_energy":  "可再生能源占比 (%)",
}
available_vars = [v for v in VAR_LABELS if v in panel.columns]
label_to_var   = {v: k for k, v in VAR_LABELS.items() if k in panel.columns}
var_to_label   = {k: v for k, v in VAR_LABELS.items() if k in panel.columns}

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🗺️ 世界地图", "📈 趋势图", "🔵 散点图", "🔥 相关性热图", "📋 描述统计"]
)

# ── Tab 1: 世界地图 ───────────────────────────────────────────────────────────
with tab1:
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        map_var_label = st.selectbox("选择展示变量", list(var_to_label.values()), key="map_var")
    map_var = label_to_var[map_var_label]
    with col2:
        years = sorted(panel["year"].dropna().unique().astype(int))
        map_year = st.selectbox("选择年份", years[::-1], key="map_year")
    with col3:
        color_scale = st.selectbox("配色方案", ["Reds", "Blues", "RdYlGn_r", "Viridis", "Plasma"], key="map_color")

    df_map = panel[panel["year"] == map_year][["country_code", map_var]].dropna()

    if df_map.empty:
        st.info(f"{map_year}年 {map_var_label} 数据不足。")
    else:
        fig = px.choropleth(
            df_map,
            locations="country_code",
            color=map_var,
            color_continuous_scale=color_scale,
            labels={map_var: map_var_label},
            title=f"{map_year}年 — {map_var_label}",
        )
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=500)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"覆盖 {len(df_map)} 个国家")

# ── Tab 2: 趋势图 ─────────────────────────────────────────────────────────────
with tab2:
    col1, col2 = st.columns([1, 2])
    with col1:
        trend_var_label = st.selectbox("选择变量", list(var_to_label.values()), key="trend_var")
        trend_var = label_to_var[trend_var_label]

        if "country_name" in panel.columns:
            all_countries = sorted(panel["country_name"].dropna().unique())
        else:
            all_countries = sorted(panel["country_code"].dropna().unique())

        # Default: top resource exporters
        default_countries = ["China", "United States", "Russia", "Saudi Arabia",
                              "Nigeria", "Norway", "Brazil", "India"]
        defaults = [c for c in default_countries if c in all_countries][:5]
        selected_countries = st.multiselect("选择国家（可多选）", all_countries,
                                             default=defaults, key="trend_countries")

        group_col = st.radio("或按分组展示", ["不分组", "地区均值", "收入组均值"], key="trend_group")

    with col2:
        if group_col == "不分组" and selected_countries:
            name_col = "country_name" if "country_name" in panel.columns else "country_code"
            df_trend = panel[panel[name_col].isin(selected_countries)][
                [name_col, "year", trend_var]].dropna()
            fig = px.line(df_trend, x="year", y=trend_var, color=name_col,
                          title=f"{trend_var_label} 趋势",
                          labels={"year": "年份", trend_var: trend_var_label, name_col: "国家"})
        elif group_col == "地区均值" and "region" in panel.columns:
            df_trend = panel.groupby(["region", "year"])[trend_var].mean().reset_index()
            df_trend = df_trend[df_trend["region"].notna() & (df_trend["region"] != "")]
            fig = px.line(df_trend, x="year", y=trend_var, color="region",
                          title=f"各地区 {trend_var_label} 均值趋势",
                          labels={"year": "年份", trend_var: trend_var_label})
        elif group_col == "收入组均值" and "income_level" in panel.columns:
            df_trend = panel.groupby(["income_level", "year"])[trend_var].mean().reset_index()
            df_trend = df_trend[df_trend["income_level"].notna() & (df_trend["income_level"] != "")]
            fig = px.line(df_trend, x="year", y=trend_var, color="income_level",
                          title=f"各收入组 {trend_var_label} 均值趋势",
                          labels={"year": "年份", trend_var: trend_var_label})
        else:
            fig = go.Figure()
            fig.add_annotation(text="请选择国家或分组", xref="paper", yref="paper", x=0.5, y=0.5)

        fig.update_layout(height=450, legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)

# ── Tab 3: 散点图 ─────────────────────────────────────────────────────────────
with tab3:
    col1, col2, col3 = st.columns(3)
    with col1:
        x_label = st.selectbox("X轴变量", list(var_to_label.values()),
                                index=list(var_to_label.keys()).index("resource_rents")
                                if "resource_rents" in var_to_label else 0, key="scatter_x")
        x_var = label_to_var[x_label]
    with col2:
        y_default = list(var_to_label.keys()).index("pm25") if "pm25" in var_to_label else 1
        y_label = st.selectbox("Y轴变量", list(var_to_label.values()), index=y_default, key="scatter_y")
        y_var = label_to_var[y_label]
    with col3:
        scatter_year = st.selectbox("年份（0=全部年份均值）", [0] + years[::-1], key="scatter_year")
        log_x = st.checkbox("X轴对数", key="scatter_logx")
        log_y = st.checkbox("Y轴对数", key="scatter_logy")

    if scatter_year == 0:
        df_sc = panel.groupby("country_code")[[x_var, y_var]].mean().reset_index()
        if "country_name" in panel.columns:
            df_sc = df_sc.merge(panel[["country_code","country_name","region","income_level"]].drop_duplicates("country_code"), on="country_code", how="left")
    else:
        df_sc = panel[panel["year"] == scatter_year].copy()

    df_sc = df_sc.dropna(subset=[x_var, y_var])
    color_col = "region" if "region" in df_sc.columns else None
    hover_col = "country_name" if "country_name" in df_sc.columns else "country_code"

    fig = px.scatter(
        df_sc, x=x_var, y=y_var, color=color_col,
        hover_name=hover_col, trendline="ols",
        log_x=log_x, log_y=log_y,
        labels={x_var: x_label, y_var: y_label},
        title=f"{x_label} vs {y_label}" + (f" ({scatter_year})" if scatter_year else " (全期均值)"),
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"样本量：{len(df_sc)} 个国家")

# ── Tab 4: 相关性热图 ─────────────────────────────────────────────────────────
with tab4:
    selected_vars = st.multiselect(
        "选择变量（建议 5–12 个）",
        options=available_vars,
        default=[v for v in ["resource_rents","pm25","co2_pc","airpol_mortality",
                              "gdp_pc_ppp","urbanization","corruption_control"] if v in available_vars],
        format_func=lambda v: var_to_label.get(v, v),
        key="corr_vars",
    )
    if len(selected_vars) >= 2:
        corr = correlation_matrix(panel, selected_vars)
        labels_list = [var_to_label.get(v, v) for v in corr.columns]
        fig = px.imshow(
            corr.values, x=labels_list, y=labels_list,
            color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
            text_auto=".2f", title="皮尔逊相关系数矩阵", height=550,
        )
        fig.update_layout(margin=dict(l=120, b=120))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("请至少选择2个变量。")

# ── Tab 5: 描述统计 ───────────────────────────────────────────────────────────
with tab5:
    desc_vars = st.multiselect(
        "选择变量",
        options=available_vars,
        default=available_vars[:10],
        format_func=lambda v: var_to_label.get(v, v),
        key="desc_vars",
    )
    if desc_vars:
        desc = descriptive_stats(panel, desc_vars)
        desc.index = [var_to_label.get(v, v) for v in desc.index]
        st.dataframe(desc, use_container_width=True)

        csv = desc.to_csv().encode("utf-8-sig")
        st.download_button("导出描述统计 (CSV)", data=csv,
                           file_name="descriptive_stats.csv", mime="text/csv")
