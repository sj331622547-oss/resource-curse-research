import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils.db import load_data, table_exists
from utils.stats import mediation_analysis, run_panel_regression

st.set_page_config(page_title="机制检验", page_icon="🔍", layout="wide")
st.title("🔍 机制检验")
st.caption("中介效应（Sobel检验）+ 异质性分析")

if not table_exists("panel_dataset"):
    st.warning("请先完成数据采集并构建面板数据集。")
    st.stop()

panel = load_data("panel_dataset")
if panel.empty:
    st.warning("数据集为空。")
    st.stop()

numeric_cols = panel.select_dtypes(include="number").columns.tolist()
numeric_cols = [c for c in numeric_cols if c != "year"]

VAR_LABELS = {
    "resource_rents":     "总资源租金",
    "oil_rents":          "石油租金",
    "gas_rents":          "天然气租金",
    "pm25":               "PM2.5",
    "co2_pc":             "CO2排放",
    "airpol_mortality":   "大气污染死亡率",
    "death_rate":         "粗死亡率",
    "ln_gdp_pc":          "ln(人均GDP)",
    "urbanization":       "城镇化率",
    "trade_gdp":          "贸易开放度",
    "corruption_control": "腐败控制",
    "govt_effectiveness": "政府效能",
    "rule_of_law":        "法治指数",
    "manufacturing_share":"制造业占比",
    "renewable_energy":   "可再生能源",
    "energy_use":         "能源消耗",
    "coal_electricity":   "煤电占比",
}

def fmt(v):
    return VAR_LABELS.get(v, v)

tab1, tab2 = st.tabs(["🔗 中介效应分析", "📊 异质性分析"])

# ── Tab 1: 中介效应 ───────────────────────────────────────────────────────────
with tab1:
    st.markdown("""
    **Baron-Kenny三步法 + Sobel检验**

    检验路径：**资源依赖 → 中介变量 → 大气污染/死亡率**
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        treatment = st.selectbox("处理变量（资源依赖）",
            options=numeric_cols,
            index=numeric_cols.index("resource_rents") if "resource_rents" in numeric_cols else 0,
            format_func=fmt, key="med_treat")
    with col2:
        mediator_opts = [v for v in numeric_cols if v != treatment]
        med_default = [v for v in ["corruption_control","manufacturing_share","coal_electricity"]
                       if v in mediator_opts]
        mediator = st.selectbox("中介变量（机制路径）",
            options=mediator_opts,
            index=mediator_opts.index(med_default[0]) if med_default else 0,
            format_func=fmt, key="med_mediator")
    with col3:
        outcome_opts = [v for v in numeric_cols if v not in [treatment, mediator]]
        outcome = st.selectbox("结果变量（大气环境/死亡）",
            options=outcome_opts,
            index=outcome_opts.index("pm25") if "pm25" in outcome_opts else 0,
            format_func=fmt, key="med_outcome")

    default_ctrl = [v for v in ["ln_gdp_pc","urbanization","trade_gdp"]
                    if v in numeric_cols and v not in [treatment, mediator, outcome]]
    controls = st.multiselect("控制变量",
        options=[v for v in numeric_cols if v not in [treatment, mediator, outcome]],
        default=default_ctrl, format_func=fmt, key="med_ctrl")

    if st.button("运行中介效应分析", type="primary"):
        with st.spinner("正在计算三步法回归…"):
            res = mediation_analysis(panel, treatment, mediator, outcome, controls)
        st.session_state["med_result"] = res

    if "med_result" in st.session_state:
        res = st.session_state["med_result"]
        if "error" in res:
            st.error(f"计算失败：{res['error']}")
        else:
            st.subheader("中介效应结果")

            # Summary metrics
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("总效应 (c)", res["total_effect"])
            c2.metric("直接效应 (c')", res["direct_effect"])
            c3.metric("间接效应 (a×b)", res["indirect_effect"])
            c4.metric("Sobel Z统计量", res["sobel_z"])
            c5.metric("中介占比", f"{res['mediation_pct']}%")

            sig = "显著" if abs(res["sobel_z"]) > 1.96 else "不显著"
            pval = res["sobel_p"]
            st.info(f"Sobel检验：Z = {res['sobel_z']}, p = {pval} → 中介效应 **{sig}**（p {'<' if pval < 0.05 else '>'} 0.05）")

            # Path diagram
            fig = go.Figure()
            nodes_x = [0.1, 0.5, 0.9, 0.5]
            nodes_y = [0.5, 0.9, 0.5, 0.1]
            labels_nodes = [fmt(treatment), fmt(mediator), fmt(outcome), ""]

            for i, (x, y, lbl) in enumerate(zip(nodes_x[:3], nodes_y[:3], labels_nodes[:3])):
                fig.add_annotation(x=x, y=y, text=f"<b>{lbl}</b>",
                                   showarrow=False, xref="paper", yref="paper",
                                   bgcolor="lightblue", bordercolor="navy",
                                   borderwidth=2, borderpad=6)
            # Arrows
            arrows = [
                (0.1, 0.5, 0.5, 0.9, f"a={res['total_effect']}"),
                (0.5, 0.9, 0.9, 0.5, f"b"),
                (0.1, 0.5, 0.9, 0.5, f"c'={res['direct_effect']}"),
            ]
            for x0, y0, x1, y1, lbl in arrows:
                fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0,
                                   xref="paper", yref="paper", axref="paper", ayref="paper",
                                   arrowhead=2, arrowwidth=2, arrowcolor="navy",
                                   text=lbl, showarrow=True)
            fig.update_layout(height=350, showlegend=False,
                               xaxis=dict(visible=False), yaxis=dict(visible=False),
                               plot_bgcolor="white", margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

            # Three-step tables
            st.markdown("**Baron-Kenny三步回归结果**")
            for step_label, step_res in [
                (f"Step 1：{fmt(treatment)} → {fmt(outcome)}（总效应）", res["step1"]),
                (f"Step 2：{fmt(treatment)} → {fmt(mediator)}", res["step2"]),
                (f"Step 3：{fmt(treatment)} + {fmt(mediator)} → {fmt(outcome)}（直接效应）", res["step3"]),
            ]:
                with st.expander(step_label):
                    step_copy = step_res.copy()
                    step_copy["变量"] = step_copy["变量"].apply(fmt)
                    st.dataframe(step_copy, use_container_width=True, hide_index=True)


# ── Tab 2: 异质性分析 ─────────────────────────────────────────────────────────
with tab2:
    st.markdown("""
    按**收入组**或**地区**分组回归，检验资源诅咒效应的异质性。
    """)

    col1, col2 = st.columns(2)
    with col1:
        het_y = st.selectbox("因变量", numeric_cols,
                              index=numeric_cols.index("pm25") if "pm25" in numeric_cols else 0,
                              format_func=fmt, key="het_y")
        het_x = st.selectbox("核心自变量", [v for v in numeric_cols if v != het_y],
                              index=0, format_func=fmt, key="het_x")
        het_ctrl = st.multiselect("控制变量",
            [v for v in numeric_cols if v not in [het_y, het_x]],
            default=[v for v in ["ln_gdp_pc","urbanization","trade_gdp"] if v in numeric_cols],
            format_func=fmt, key="het_ctrl")
    with col2:
        group_by = st.radio("分组依据", ["收入组 (income_level)", "地区 (region)"], key="het_group")
        group_col = "income_level" if "收入" in group_by else "region"

    if st.button("运行异质性分析", type="primary"):
        if group_col not in panel.columns:
            st.error(f"数据集中没有 {group_col} 列，请先采集国家元数据。")
        else:
            groups = sorted(panel[group_col].dropna().unique())
            all_x  = [het_x] + het_ctrl
            results_list = []

            prog = st.progress(0)
            for i, grp in enumerate(groups):
                sub = panel[panel[group_col] == grp]
                res = run_panel_regression(sub, het_y, all_x)
                if "error" not in res:
                    row = res["table"][res["table"]["变量"] == het_x].copy()
                    if not row.empty:
                        results_list.append({
                            "分组":   grp,
                            "系数":   float(row["系数"].iloc[0]),
                            "标准误": float(row["标准误"].iloc[0]),
                            "p值":    float(row["p值"].iloc[0]),
                            "观测值": res["n_obs"],
                            "显著性": row["显著性"].iloc[0],
                        })
                prog.progress((i + 1) / len(groups))

            if results_list:
                df_het = pd.DataFrame(results_list)
                st.session_state["het_result"] = df_het
            else:
                st.warning("各子样本数据量不足，无法完成回归。")

    if "het_result" in st.session_state:
        df_het = st.session_state["het_result"]
        st.subheader("异质性回归结果")
        st.dataframe(df_het, use_container_width=True, hide_index=True)

        # Forest plot
        df_het = df_het.sort_values("系数", ascending=True)
        fig = go.Figure()
        colors = ["red" if p < 0.05 else "gray" for p in df_het["p值"]]
        fig.add_trace(go.Scatter(
            x=df_het["系数"], y=df_het["分组"],
            mode="markers",
            marker=dict(size=12, color=colors),
            error_x=dict(type="data", array=(1.96 * df_het["标准误"]).values, visible=True),
            text=[f"n={n}" for n in df_het["观测值"]],
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="black")
        fig.update_layout(
            title=f"分组回归：{fmt(het_x)} 对 {fmt(het_y)} 的影响（红色=p<0.05）",
            xaxis_title="系数", yaxis_title=group_col,
            height=max(350, len(df_het) * 50 + 100),
        )
        st.plotly_chart(fig, use_container_width=True)

        csv = df_het.to_csv(index=False).encode("utf-8-sig")
        st.download_button("导出异质性结果 (CSV)", data=csv,
                           file_name="heterogeneity_results.csv", mime="text/csv")
