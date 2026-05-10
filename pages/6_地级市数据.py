import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils.china_collector import (
    ALL_CITIES, CITY_PROVINCE_MAP,
    fetch_city_aqi, build_city_panel,
    get_city_nbs_template, get_city_resource_template,
)
from utils.db import load_data, table_exists, save_data
from utils.stats import run_panel_regression

st.set_page_config(page_title="地级市数据", page_icon="🏙️", layout="wide")
st.title("🏙️ 地级市面板数据")
st.caption(f"覆盖 {len(ALL_CITIES)} 个重点城市 | AQI自动采集 + NBS经济数据上传")

tab1, tab2, tab3, tab4 = st.tabs(["📥 数据采集", "🗺️ 城市看板", "📈 城市回归", "📋 数据说明"])

# ════════════════════════════════════════════════════════════════════════════
# Tab 1: 数据采集
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Step 1: AQI 自动采集 ──────────────────────────────────────────────
    st.subheader("Step 1 — 城市AQI/PM2.5 自动采集（akshare）")
    st.markdown(f"""
    自动从生态环境部获取 **{len(ALL_CITIES)} 个重点城市** 的历史空气质量数据：
    AQI、PM2.5、PM10、SO₂、NO₂、O₃，保留城市粒度（不汇总到省）。
    > ⏱ 约需 **10–20 分钟**，数据从 **2015年** 起有效。
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        aqi_start = st.number_input("起始年份", 2015, 2020, 2015, key="city_aqi_start")
    with col2:
        aqi_end = st.number_input("结束年份", 2016, 2023, 2022, key="city_aqi_end")
    with col3:
        st.markdown("&nbsp;")
        fetch_btn = st.button("🚀 开始采集城市AQI", type="primary", use_container_width=True)

    if fetch_btn:
        st.info("正在逐城市采集，请勿关闭页面…")
        prog = st.progress(0)
        stat = st.empty()
        n = fetch_city_aqi(int(aqi_start), int(aqi_end), progress_bar=prog, status_text=stat)
        stat.empty()
        st.success(f"采集完成！共 {n:,} 条城市-年份记录。") if n > 0 else \
            st.warning("采集结果为空，请检查网络后重试。")

    if table_exists("raw_city_aqi"):
        aqi = load_data("raw_city_aqi")
        if not aqi.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("记录数", f"{len(aqi):,}")
            c2.metric("城市数", aqi["city"].nunique())
            c3.metric("年份范围", f"{int(aqi['year'].min())}–{int(aqi['year'].max())}")
            c4.metric("含PM2.5城市", aqi["pm25"].notna().sum() if "pm25" in aqi.columns else 0)

    st.divider()

    # ── Step 2: NBS城市经济数据 ───────────────────────────────────────────
    st.subheader("Step 2 — NBS城市经济数据（手动下载后上传）")

    with st.expander("📋 如何从国家统计局下载城市数据（点击展开）", expanded=True):
        st.markdown("""
        **下载步骤：**
        1. 打开：[https://data.stats.gov.cn/easyquery.htm?cn=E0103](https://data.stats.gov.cn/easyquery.htm?cn=E0103)
        2. 左侧选择「城市」→「城市年度数据」
        3. 选择指标：**GDP、人均GDP、人口、城镇化率、工业增加值**
        4. 选择时间范围：2003–2022
        5. 右上角点击「下载」→「Excel格式」
        6. 整理为下方模板格式后上传

        **关键列名（必须包含）：** `city`（城市名）、`year`（年份）、`gdp_bn_cny`（GDP亿元）
        """)
        tpl = get_city_nbs_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载NBS城市数据填写模板", data=tpl,
                           file_name="city_nbs_template.csv", mime="text/csv")

    nbs_file = st.file_uploader("上传NBS城市经济数据（CSV）", type="csv", key="city_nbs_up")
    if nbs_file:
        df_nbs = pd.read_csv(nbs_file)
        st.dataframe(df_nbs.head(10), use_container_width=True, hide_index=True)
        if st.button("保存NBS城市数据"):
            save_data(df_nbs, "city_nbs_upload", if_exists="replace")
            st.success(f"已保存 {len(df_nbs):,} 条记录。")

    st.divider()

    # ── Step 3: 城市资源数据 ──────────────────────────────────────────────
    st.subheader("Step 3 — 城市资源依赖数据（手动整理上传）")

    with st.expander("📋 数据来源说明"):
        st.markdown("""
        **推荐数据来源：**
        - **《中国城市统计年鉴》**：采矿业产值、工业结构
          → [https://data.stats.gov.cn/](https://data.stats.gov.cn/)
        - **《中国能源统计年鉴》**：分城市能源生产数据
        - **各省统计年鉴**：分城市煤油气产量

        **资源型城市名单参考：** 国务院2013年发布的《全国资源型城市可持续发展规划》
        中262个资源型城市名单（可作为工具变量的依据）
        """)
        tpl2 = get_city_resource_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载资源数据填写模板", data=tpl2,
                           file_name="city_resource_template.csv", mime="text/csv")

    res_file = st.file_uploader("上传城市资源数据（CSV）", type="csv", key="city_res_up")
    if res_file:
        df_res = pd.read_csv(res_file)
        st.dataframe(df_res.head(10), use_container_width=True, hide_index=True)
        if st.button("保存资源数据"):
            save_data(df_res, "city_resource_upload", if_exists="replace")
            st.success(f"已保存 {len(df_res):,} 条记录。")

    st.divider()

    # ── Step 4: CHAP城市级PM2.5 ─────────────────────────────────────────
    st.subheader("Step 4 — CHAP高精度PM2.5数据（可选）")

    with st.expander("📋 CHAP城市级数据下载说明"):
        st.markdown("""
        CHAP数据集提供**地级市级别**年均PM2.5（卫星反演，精度更高，覆盖2000–2020年）：

        1. 打开：[https://weijing-rs.github.io/CHAP.html](https://weijing-rs.github.io/CHAP.html)
        2. 下载 **"City level annual mean PM2.5"**
        3. 整理格式：`city`、`year`、`pm25_annual`（μg/m³）
        """)

    pm25_file = st.file_uploader("上传CHAP城市PM2.5（CSV）", type="csv", key="city_pm25_up")
    if pm25_file:
        df_pm25 = pd.read_csv(pm25_file)
        st.dataframe(df_pm25.head(), use_container_width=True, hide_index=True)
        if st.button("保存城市PM2.5"):
            save_data(df_pm25, "city_pm25_upload", if_exists="replace")
            st.success(f"已保存 {len(df_pm25):,} 条记录。")

    st.divider()

    # ── Step 5: 构建面板 ─────────────────────────────────────────────────
    st.subheader("Step 5 — 构建城市面板数据集")
    can_build = table_exists("raw_city_aqi") or table_exists("city_nbs_upload")

    if st.button("🔨 构建城市面板数据集", type="primary", disabled=not can_build):
        with st.spinner("合并数据中…"):
            panel = build_city_panel()
        st.success(f"完成！共 {len(panel):,} 个城市-年份观测值。") if not panel.empty \
            else st.error("数据不足，请先完成至少Step 1或Step 2。")

    if table_exists("city_panel"):
        cp = load_data("city_panel")
        if not cp.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("观测值", f"{len(cp):,}")
            c2.metric("城市数", cp["city"].nunique())
            c3.metric("年份范围",
                      f"{int(cp['year'].min())}–{int(cp['year'].max())}")
            csv = cp.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 导出城市面板数据（CSV）", data=csv,
                               file_name="city_panel.csv", mime="text/csv")


# ════════════════════════════════════════════════════════════════════════════
# Tab 2: 城市看板
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if not table_exists("city_panel") and not table_exists("raw_city_aqi"):
        st.info("请先完成Tab1数据采集。")
        st.stop()

    src = "city_panel" if table_exists("city_panel") else "raw_city_aqi"
    cp = load_data(src)
    if cp.empty:
        st.stop()

    num_cols = [c for c in cp.select_dtypes(include="number").columns if c != "year"]
    VAR_ZH = {
        "aqi":"AQI年均值","pm25":"PM2.5(μg/m³)","pm10":"PM10(μg/m³)",
        "so2":"SO₂(μg/m³)","no2":"NO₂(μg/m³)","o3":"O₃(μg/m³)",
        "gdp_bn_cny":"GDP(亿元)","gdp_per_capita_cny":"人均GDP(元)",
        "population_10k":"人口(万人)","urbanization":"城镇化率(%)",
        "mining_output_bn":"采矿业产值(亿元)","mining_share":"采矿业占比(%)",
        "ln_gdp_pc":"ln(人均GDP)","obs_days":"有效观测天数",
    }
    def fz(v): return VAR_ZH.get(v, v)

    subtab1, subtab2, subtab3 = st.tabs(["🏆 城市排名", "📈 趋势", "🔵 散点"])

    with subtab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            bv = st.selectbox("变量", num_cols, format_func=fz, key="city_bv")
        with col2:
            yrs = sorted(cp["year"].dropna().unique().astype(int))
            by = st.selectbox("年份", yrs[::-1], key="city_by")
        with col3:
            top_n = st.slider("显示城市数", 10, min(100, cp["city"].nunique()), 30)
        with col1:
            sort_asc = st.checkbox("升序排列（最低污染）", value=False)

        df_b = (cp[cp["year"] == by][["city", "province", bv]].dropna()
                .sort_values(bv, ascending=sort_asc).head(top_n))
        if not df_b.empty:
            fig = px.bar(df_b, x=bv, y="city", orientation="h",
                         color="province", title=f"{by}年 {fz(bv)} — 城市排名",
                         labels={bv: fz(bv), "city": "城市"})
            fig.update_layout(height=max(400, top_n * 22),
                              yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with subtab2:
        col1, col2 = st.columns([1, 2])
        with col1:
            tv = st.selectbox("变量", num_cols, format_func=fz, key="city_tv")
            city_list = sorted(cp["city"].unique())
            defaults = [c for c in ["北京","上海","广州","大庆","太原","乌鲁木齐"]
                        if c in city_list][:6]
            sel = st.multiselect("选择城市", city_list, default=defaults)
        with col2:
            if sel:
                df_t = cp[cp["city"].isin(sel)][["city","year",tv]].dropna()
                fig = px.line(df_t, x="year", y=tv, color="city",
                              title=f"{fz(tv)} 城市趋势",
                              labels={"year":"年份", tv:fz(tv)})
                fig.update_layout(height=420)
                st.plotly_chart(fig, use_container_width=True)

    with subtab3:
        col1, col2, col3 = st.columns(3)
        with col1:
            sx = st.selectbox("X轴", num_cols, format_func=fz, key="city_sx")
        with col2:
            sy_opts = [v for v in num_cols if v != sx]
            sy = st.selectbox("Y轴", sy_opts,
                              index=sy_opts.index("pm25") if "pm25" in sy_opts else 0,
                              format_func=fz, key="city_sy")
        with col3:
            sc_yr = st.selectbox("年份（0=全期均值）", [0]+yrs[::-1], key="city_sc_yr")

        df_sc = (cp.groupby("city")[[sx,sy,"province"]].mean().reset_index()
                 if sc_yr == 0 else cp[cp["year"]==sc_yr].copy())
        df_sc = df_sc.dropna(subset=[sx, sy])
        if not df_sc.empty:
            prov_col = "province" if "province" in df_sc.columns else None
            fig = px.scatter(df_sc, x=sx, y=sy, color=prov_col,
                             hover_name="city", trendline="ols",
                             title=f"{fz(sx)} vs {fz(sy)}",
                             labels={sx:fz(sx), sy:fz(sy)})
            fig.update_layout(height=480)
            st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 3: 城市回归
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not table_exists("city_panel"):
        st.info("请先构建城市面板数据集（Tab1 Step 5）。")
        st.stop()

    cp = load_data("city_panel")
    if cp.empty:
        st.stop()

    num_cols2 = [c for c in cp.select_dtypes(include="number").columns if c != "year"]
    def fz2(v): return VAR_ZH.get(v, v)

    col1, col2 = st.columns(2)
    with col1:
        ry = st.selectbox("因变量", num_cols2,
                          index=num_cols2.index("pm25") if "pm25" in num_cols2 else 0,
                          format_func=fz2, key="city_ry")
        rx_opts = [v for v in num_cols2 if v != ry]
        rx = st.multiselect("核心自变量（资源依赖）", rx_opts,
                            default=[v for v in ["mining_share","mining_output_bn"]
                                     if v in rx_opts],
                            format_func=fz2, key="city_rx")
        rc_opts = [v for v in rx_opts if v not in rx]
        rc = st.multiselect("控制变量", rc_opts,
                            default=[v for v in ["ln_gdp_pc","urbanization"]
                                     if v in rc_opts],
                            format_func=fz2, key="city_rc")
    with col2:
        c_efe = st.checkbox("城市固定效应", value=True, key="city_efe")
        c_tfe = st.checkbox("年份固定效应", value=True, key="city_tfe")
        c_cl  = st.checkbox("聚类标准误（按城市）", value=True, key="city_cl")

        prov_filter = st.selectbox(
            "按省份筛选",
            ["全部"] + sorted(cp["province"].dropna().unique()) if "province" in cp.columns else ["全部"],
            key="city_prov_f")
        cp_sub = cp if prov_filter == "全部" else cp[cp["province"] == prov_filter]

    if st.button("运行城市回归", type="primary"):
        all_x = rx + rc
        if not all_x:
            st.warning("请选择自变量。")
        else:
            with st.spinner("计算中…"):
                res = run_panel_regression(cp_sub, ry, all_x,
                                           entity_col="city", time_col="year",
                                           entity_effects=c_efe, time_effects=c_tfe,
                                           cluster_entity=c_cl)
            if "error" in res:
                st.error(res["error"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("观测值", res["n_obs"])
                c2.metric("城市数", res["n_entities"])
                c3.metric("组内R²", res["r2_within"])
                tbl = res["table"].copy()
                tbl["变量"] = tbl["变量"].apply(fz2)
                st.dataframe(tbl, use_container_width=True, hide_index=True)
                st.caption("*** p<0.01  ** p<0.05  * p<0.1")
                csv = tbl.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇️ 导出结果", data=csv,
                                   file_name="city_regression.csv", mime="text/csv")


# ════════════════════════════════════════════════════════════════════════════
# Tab 4: 数据说明
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown(f"""
    ### 数据来源

    | 数据 | 来源 | 自动/手动 | 年份 |
    |------|------|----------|------|
    | AQI、PM2.5、SO₂、NO₂、O₃ | 生态环境部/akshare | ✅ 自动 | 2015– |
    | GDP、人均GDP、人口 | 国家统计局城市年度数据 | 📁 手动上传 | 2003– |
    | 采矿业产值、煤油气产量 | 城市/省份统计年鉴 | 📁 手动上传 | 2003– |
    | PM2.5卫星（高精度） | CHAP数据集 | 📁 手动上传 | 2000–2020 |

    ### 城市范围（{len(ALL_CITIES)}个重点城市）

    覆盖全国31个省份的主要地级市，包括：
    - 所有省会城市、直辖市
    - 主要资源型城市（大庆、鄂尔多斯、克拉玛依等）
    - 生态环境部AQI监测的168个重点城市

    ### 在论文中的使用方式

    > *"We extend the analysis to {len(ALL_CITIES)} Chinese prefecture-level cities
    > to exploit within-country variation. The city-level panel allows us to control
    > for time-invariant provincial characteristics while identifying the causal
    > effect of resource dependence on air quality..."*

    ### 关键变量
    | 变量 | 含义 | 论文作用 |
    |------|------|---------|
    | `mining_share` | 采矿业占GDP比重(%) | 资源依赖度（自变量） |
    | `pm25` | AQI中PM2.5浓度 | 大气污染（因变量） |
    | `aqi` | 空气质量综合指数 | 大气清洁能力（因变量） |
    | `ln_gdp_pc` | ln(人均GDP) | 发展水平（控制变量） |
    """)
