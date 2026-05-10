import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils.china_collector import (
    get_county_pm25_template, get_county_economic_template,
    build_county_panel,
)
from utils.db import load_data, table_exists, save_data
from utils.stats import run_panel_regression, descriptive_stats

st.set_page_config(page_title="县级数据", page_icon="🏘️", layout="wide")
st.title("🏘️ 县级面板数据")
st.caption("2800+ 县市区 | CHAP卫星PM2.5 + 县域统计年鉴 + 手动上传")

# ── 数据说明横幅 ──────────────────────────────────────────────────────────────
st.info("""
**县级数据说明：** 由于国家统计局API不开放县级数据接口，县级数据需手动下载后上传。
主要数据来源：① **CHAP卫星PM2.5**（2800+县，2000–2020年，免费）
② **《中国县域统计年鉴》**（经济/资源数据，需购买或图书馆查阅）
③ **各省统计年鉴**（部分县级经济数据，部分免费）
""")

tab1, tab2, tab3, tab4 = st.tabs(["📥 数据上传", "🗺️ 县级看板", "📈 县级回归", "📋 数据说明"])

# ════════════════════════════════════════════════════════════════════════════
# Tab 1: 数据上传
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Step 1: CHAP PM2.5（核心数据）────────────────────────────────────
    st.subheader("Step 1 — CHAP 县级PM2.5数据（最重要）")
    st.markdown("""
    **CHAP（中国高分辨率大气污染数据集）** 是本研究最重要的县级数据来源：
    - 覆盖：**全国2800+县市区**，年均PM2.5（μg/m³）
    - 时间：**2000–2020年**
    - 分辨率：基于卫星反演（1km × 1km）
    - 费用：**完全免费**
    """)

    with st.expander("📋 CHAP县级数据下载步骤（点击展开）", expanded=True):
        st.markdown("""
        **第一步：** 打开 [https://weijing-rs.github.io/CHAP.html](https://weijing-rs.github.io/CHAP.html)

        **第二步：** 在页面中找到 **"County level annual mean PM2.5"** 并下载CSV

        **第三步：** 文件通常包含以下列，整理为下方模板格式：
        | county_code | county_name | city | province | year | pm25_annual |
        |-------------|-------------|------|----------|------|-------------|
        | 110101 | 东城区 | 北京 | 北京 | 2019 | 41.2 |

        **第四步：** 上传到下方
        """)
        tpl1 = get_county_pm25_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载县级PM2.5填写模板", data=tpl1,
                           file_name="county_pm25_template.csv", mime="text/csv")

    pm25_file = st.file_uploader("上传CHAP县级PM2.5数据（CSV）",
                                  type="csv", key="county_pm25")
    if pm25_file:
        df = pd.read_csv(pm25_file)
        c1, c2, c3 = st.columns(3)
        c1.metric("行数", len(df))
        c2.metric("县数", df["county_name"].nunique() if "county_name" in df.columns
                  else df.iloc[:, 1].nunique())
        c3.metric("列数", len(df.columns))
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        if st.button("保存PM2.5数据", type="primary"):
            save_data(df, "county_pm25_upload", if_exists="replace")
            st.success(f"✅ 已保存 {len(df):,} 条县级PM2.5记录！")

    if table_exists("county_pm25_upload"):
        df_check = load_data("county_pm25_upload")
        if not df_check.empty:
            st.success(f"**已有PM2.5数据：** {len(df_check):,} 条记录，"
                       f"{df_check['county_name'].nunique() if 'county_name' in df_check.columns else '?'} 个县")

    st.divider()

    # ── Step 2: 县级经济/资源数据 ─────────────────────────────────────────
    st.subheader("Step 2 — 县级经济与资源数据（手动整理）")

    with st.expander("📋 数据来源与获取方法"):
        st.markdown("""
        **推荐数据来源（按获取难度排序）：**

        | 来源 | 数据内容 | 获取方式 | 费用 |
        |------|---------|---------|------|
        | 各省统计年鉴 | GDP、人口、工业结构 | 省统计局官网免费下载 | 免费 |
        | 《中国县域统计年鉴》 | 完整经济指标 | 图书馆/购买 | 收费 |
        | 《中国县域经济数据库》 | GDP、财政、工业 | CNRDS/CSMAR | 高校免费 |
        | 资源税数据 | 分县资源税收入 | 地方税务局公开数据 | 免费 |

        **重要提示：** 如果所在高校订阅了 **CNRDS**（中国研究数据服务平台）
        或 **CSMAR**（国泰安），可直接下载完整县级面板数据。
        """)
        tpl2 = get_county_economic_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载县级经济数据填写模板", data=tpl2,
                           file_name="county_economic_template.csv", mime="text/csv")

    eco_file = st.file_uploader("上传县级经济数据（CSV）", type="csv", key="county_eco")
    if eco_file:
        df_eco = pd.read_csv(eco_file)
        st.dataframe(df_eco.head(10), use_container_width=True, hide_index=True)
        if st.button("保存经济数据"):
            save_data(df_eco, "county_economic_upload", if_exists="replace")
            st.success(f"✅ 已保存 {len(df_eco):,} 条记录。")

    st.divider()

    # ── Step 3: 构建县级面板 ──────────────────────────────────────────────
    st.subheader("Step 3 — 构建县级面板数据集")

    has_data = (table_exists("county_pm25_upload") or
                table_exists("county_economic_upload"))

    if st.button("🔨 构建县级面板", type="primary", disabled=not has_data):
        with st.spinner("合并数据中…"):
            panel = build_county_panel()
        if not panel.empty:
            st.success(f"✅ 完成！共 {len(panel):,} 个县-年份观测值，"
                       f"覆盖 {panel['county_name'].nunique() if 'county_name' in panel.columns else '?'} 个县。")
        else:
            st.error("数据不足，请先上传PM2.5或经济数据。")

    if table_exists("county_panel"):
        cp = load_data("county_panel")
        if not cp.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("观测值", f"{len(cp):,}")
            if "county_name" in cp.columns:
                c2.metric("县数", cp["county_name"].nunique())
            if "province" in cp.columns:
                c3.metric("省份数", cp["province"].nunique())
            c4.metric("年份范围",
                      f"{int(cp['year'].min())}–{int(cp['year'].max())}")
            with st.expander("预览数据（前20行）"):
                st.dataframe(cp.head(20), use_container_width=True, hide_index=True)
            csv = cp.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 导出县级面板数据（CSV）", data=csv,
                               file_name="county_panel.csv", mime="text/csv")

# ════════════════════════════════════════════════════════════════════════════
# Tab 2: 县级看板
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if not table_exists("county_panel"):
        st.info("请先完成Tab1的数据上传和面板构建。")
        st.stop()

    cp = load_data("county_panel")
    if cp.empty:
        st.info("面板数据为空。")
        st.stop()

    num_cols = [c for c in cp.select_dtypes(include="number").columns if c != "year"]
    VAR_ZH = {
        "pm25_annual": "PM2.5年均值(μg/m³)",
        "pm25_max":    "PM2.5最大月均值",
        "gdp_bn_cny":  "GDP(亿元)",
        "gdp_per_capita_cny": "人均GDP(元)",
        "population_10k": "人口(万人)",
        "industry_share": "工业占比(%)",
        "mining_output_bn": "采矿业产值(亿元)",
        "mining_share": "采矿业占GDP比重(%)",
        "fiscal_revenue_mn": "财政收入(百万元)",
        "ln_gdp_pc":   "ln(人均GDP)",
    }
    def fz(v): return VAR_ZH.get(v, v)

    subtab1, subtab2, subtab3 = st.tabs(["🏆 县域排名", "📈 省内分布", "🔵 散点图"])

    with subtab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            bv = st.selectbox("变量", num_cols, format_func=fz, key="co_bv")
        with col2:
            yrs = sorted(cp["year"].dropna().unique().astype(int))
            by = st.selectbox("年份", yrs[::-1], key="co_by")
        with col3:
            top_n = st.slider("显示县数", 20, min(200, len(cp)), 50, key="co_top")

        sort_asc = st.checkbox("升序（最清洁）", key="co_asc")
        name_col = "county_name" if "county_name" in cp.columns else cp.columns[0]
        df_b = (cp[cp["year"] == by][[name_col, "province" if "province" in cp.columns else name_col, bv]]
                .dropna().sort_values(bv, ascending=sort_asc).head(top_n))
        if not df_b.empty:
            color_col = "province" if "province" in df_b.columns else None
            fig = px.bar(df_b, x=bv, y=name_col, orientation="h",
                         color=color_col,
                         title=f"{by}年 {fz(bv)} — 县域排名（Top{top_n}）",
                         labels={bv: fz(bv), name_col: "县区"})
            fig.update_layout(height=max(400, top_n * 20),
                              yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with subtab2:
        if "province" in cp.columns:
            col1, col2 = st.columns([1, 2])
            with col1:
                pv = st.selectbox("变量", num_cols, format_func=fz, key="co_pv")
                yr_box = st.selectbox("年份", yrs[::-1], key="co_yr_box")
                prov_sel = st.multiselect("选择省份",
                                          sorted(cp["province"].dropna().unique()),
                                          default=["北京","广东","山西","新疆"])
            with col2:
                df_box = cp[(cp["year"] == yr_box) &
                            (cp["province"].isin(prov_sel))][[pv, "province"]].dropna()
                if not df_box.empty:
                    fig = px.box(df_box, x="province", y=pv, color="province",
                                 title=f"{yr_box}年各省县域 {fz(pv)} 分布",
                                 labels={pv: fz(pv), "province": "省份"})
                    fig.update_layout(height=420, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("需要province列才能显示省内分布。")

    with subtab3:
        col1, col2 = st.columns(2)
        with col1:
            sx = st.selectbox("X轴", num_cols, format_func=fz, key="co_sx")
        with col2:
            sy_opts = [v for v in num_cols if v != sx]
            sy = st.selectbox("Y轴", sy_opts,
                              index=sy_opts.index("pm25_annual")
                              if "pm25_annual" in sy_opts else 0,
                              format_func=fz, key="co_sy")
        sc_yr = st.selectbox("年份（0=全期均值）", [0]+yrs[::-1], key="co_sc_yr")

        name_col2 = "county_name" if "county_name" in cp.columns else cp.columns[0]
        df_sc = (cp.groupby(name_col2)[[sx, sy]].mean().reset_index()
                 if sc_yr == 0 else cp[cp["year"] == sc_yr])
        df_sc = df_sc.dropna(subset=[sx, sy])
        if not df_sc.empty:
            fig = px.scatter(df_sc, x=sx, y=sy, trendline="ols",
                             hover_name=name_col2,
                             opacity=0.5,
                             title=f"{fz(sx)} vs {fz(sy)}（n={len(df_sc)}县）",
                             labels={sx: fz(sx), sy: fz(sy)})
            fig.update_layout(height=480)
            st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# Tab 3: 县级回归
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not table_exists("county_panel"):
        st.info("请先构建县级面板数据集。")
        st.stop()

    cp = load_data("county_panel")
    if cp.empty:
        st.stop()

    num_cols3 = [c for c in cp.select_dtypes(include="number").columns if c != "year"]
    entity_col = "county_name" if "county_name" in cp.columns else \
                 ("county_code" if "county_code" in cp.columns else cp.columns[0])

    def fz3(v): return VAR_ZH.get(v, v)

    col1, col2 = st.columns(2)
    with col1:
        ry = st.selectbox("因变量", num_cols3,
                          index=num_cols3.index("pm25_annual")
                          if "pm25_annual" in num_cols3 else 0,
                          format_func=fz3, key="co_ry")
        rx_opts = [v for v in num_cols3 if v != ry]
        rx = st.multiselect("核心自变量", rx_opts,
                            default=[v for v in ["mining_share", "mining_output_bn"]
                                     if v in rx_opts],
                            format_func=fz3, key="co_rx")
        rc_opts = [v for v in rx_opts if v not in rx]
        rc = st.multiselect("控制变量", rc_opts,
                            default=[v for v in ["ln_gdp_pc", "industry_share"]
                                     if v in rc_opts],
                            format_func=fz3, key="co_rc")
    with col2:
        co_efe = st.checkbox("县级固定效应", value=True)
        co_tfe = st.checkbox("年份固定效应", value=True)
        co_cl  = st.checkbox("聚类标准误（按县）", value=True)
        st.caption("⚠️ 县级面板观测值多，回归计算可能需要1–2分钟。")

    if st.button("运行县级回归", type="primary"):
        all_x = rx + rc
        if not all_x:
            st.warning("请选择自变量。")
        else:
            with st.spinner("计算中，请稍候…"):
                res = run_panel_regression(cp, ry, all_x,
                                           entity_col=entity_col, time_col="year",
                                           entity_effects=co_efe, time_effects=co_tfe,
                                           cluster_entity=co_cl)
            if "error" in res:
                st.error(res["error"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("观测值", res["n_obs"])
                c2.metric("县数", res["n_entities"])
                c3.metric("组内R²", res["r2_within"])
                tbl = res["table"].copy()
                tbl["变量"] = tbl["变量"].apply(fz3)
                st.dataframe(tbl, use_container_width=True, hide_index=True)
                st.caption("*** p<0.01  ** p<0.05  * p<0.1")
                csv = tbl.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇️ 导出结果", data=csv,
                                   file_name="county_regression.csv", mime="text/csv")

# ════════════════════════════════════════════════════════════════════════════
# Tab 4: 数据说明
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("""
    ### 县级数据体系

    | 数据层 | 覆盖 | 主要来源 | 说明 |
    |--------|------|---------|------|
    | **PM2.5卫星数据** | 2800+县，2000–2020 | CHAP | 免费，最关键 |
    | **GDP/人口** | 约2800县 | 县域统计年鉴/CNRDS | 部分免费 |
    | **采矿业产值** | 资源型县 | 省统计年鉴 | 需手动整理 |
    | **财政收入** | 约2800县 | 财政年鉴 | 部分免费 |

    ### 为什么县级数据对论文有价值？

    ```
    优势：
    ✅ 样本量大（2800县 × 20年 = 56,000观测值）
    ✅ 控制省级/市级不可观测因素
    ✅ 空间变异更丰富（资源依赖差异在县级更显著）
    ✅ CHAP PM2.5覆盖完整

    劣势：
    ⚠️ 经济数据覆盖率低于省/市级
    ⚠️ 部分指标存在较多缺失
    ⚠️ 数据整理工作量较大
    ```

    ### 推荐使用策略

    在Nature Communications论文中，县级分析建议作为：
    1. **主要稳健性检验**：展示结果在更细粒度下仍成立
    2. **机制分析**：县级资源税数据可作为工具变量
    3. **空间分析**：可结合空间计量方法

    > *"As a robustness check using finer spatial granularity,
    > we replicate the main analysis at the county level (N=2,800+)
    > using satellite-retrieved PM2.5 from the CHAP dataset..."*

    ### 数据获取优先级建议

    ```
    第一步：下载CHAP县级PM2.5（免费，30分钟）
    第二步：从CNRDS/CSMAR下载县级GDP（高校免费）
    第三步：整理各省统计年鉴采矿业数据（1-2天）
    ```
    """)
