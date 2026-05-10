import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import io
from utils.china_collector import (
    PROVINCES_31, NBS_INDICATORS,
    fetch_nbs_data, fetch_china_aqi,
    build_china_panel,
    get_pm25_template, get_health_template,
)
from utils.db import load_data, table_exists, save_data
from utils.stats import run_panel_regression, descriptive_stats

st.set_page_config(page_title="中国省级数据", page_icon="🇨🇳", layout="wide")
st.title("🇨🇳 中国省级数据")
st.caption("31省×20年面板数据 | 国家统计局 + AQI + 卫生统计")

tab1, tab2, tab3, tab4 = st.tabs([
    "📥 数据采集", "🗺️ 省级看板", "📈 省级回归", "📋 数据说明"
])

# ════════════════════════════════════════════════════════════════════════════
# Tab 1: 数据采集
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Step 1: NBS 经济/资源数据 ──────────────────────────────────────────
    st.subheader("Step 1 — 国家统计局省级数据（自动采集）")
    st.markdown("从国家统计局分省年度数据库自动获取经济、资源、排放指标。")

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_nbs = st.multiselect(
            "选择指标组",
            options=list(NBS_INDICATORS.keys()),
            default=list(NBS_INDICATORS.keys()),
        )
    with col2:
        nbs_start = st.number_input("起始年份", 2003, 2020, 2003, key="nbs_start")
        nbs_end   = st.number_input("结束年份", 2010, 2022, 2021, key="nbs_end")
        fetch_nbs_btn = st.button("开始采集NBS数据", type="primary",
                                  use_container_width=True,
                                  disabled=len(selected_nbs) == 0)

    if fetch_nbs_btn:
        st.info("正在请求国家统计局API，每个指标间隔0.5秒，请耐心等待…")
        prog = st.progress(0)
        stat = st.empty()
        n = fetch_nbs_data(selected_nbs, int(nbs_start), int(nbs_end),
                           progress_bar=prog, status_text=stat)
        stat.empty()
        if n > 0:
            st.success(f"NBS数据采集完成，共 {n:,} 条记录！")
        else:
            st.warning("采集结果为空，可能是国家统计局API暂时限流，请稍后重试。")

    if table_exists("raw_china_nbs"):
        nbs = load_data("raw_china_nbs")
        if not nbs.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("NBS记录数", f"{len(nbs):,}")
            c2.metric("省份数", nbs["province"].nunique())
            c3.metric("指标数", nbs["indicator_code"].nunique())

    st.divider()

    # ── Step 2: AQI 数据（akshare）──────────────────────────────────────────
    st.subheader("Step 2 — 城市AQI数据（自动采集，汇总至省级）")
    st.markdown("""
    通过 akshare 获取168个重点城市的历史AQI和PM2.5数据，自动按省份均值汇总。
    > ⚠️ 数据从**2015年**开始有效，采集约需 5–10 分钟（需逐城市请求）。
    """)

    col1, col2 = st.columns([2, 1])
    with col1:
        aqi_start = st.number_input("AQI起始年份", 2015, 2020, 2015, key="aqi_start")
        aqi_end   = st.number_input("AQI结束年份", 2016, 2023, 2022, key="aqi_end")
    with col2:
        st.markdown("")
        fetch_aqi_btn = st.button("开始采集AQI数据", use_container_width=True)

    if fetch_aqi_btn:
        st.info("正在逐省采集城市AQI数据，请勿关闭页面…")
        prog2 = st.progress(0)
        stat2 = st.empty()
        n2 = fetch_china_aqi(int(aqi_start), int(aqi_end),
                             progress_bar=prog2, status_text=stat2)
        stat2.empty()
        if n2 > 0:
            st.success(f"AQI数据采集完成，共 {n2:,} 条省级年度记录！")
        else:
            st.warning("AQI采集结果为空，请检查网络后重试。")

    st.divider()

    # ── Step 3: 手动上传 PM2.5 ────────────────────────────────────────────
    st.subheader("Step 3 — 上传 PM2.5 数据（推荐CHAP数据集）")

    with st.expander("📥 CHAP数据集下载说明"):
        st.markdown("""
        **CHAP（中国高分辨率大气污染数据集）** 提供2000–2020年全国所有行政单位PM2.5年均值，完全免费。

        **下载步骤：**
        1. 打开：`https://weijing-rs.github.io/CHAP.html`
        2. 下载 **Province level annual mean PM2.5**（省级年度均值CSV）
        3. 按下方模板格式整理后上传

        **列名格式要求：**
        | province | year | pm25_annual |
        |---------|------|-------------|
        | 北京 | 2019 | 42.3 |
        """)
        tpl1 = get_pm25_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("下载PM2.5填写模板", data=tpl1,
                           file_name="pm25_template.csv", mime="text/csv")

    pm25_file = st.file_uploader("上传PM2.5数据（CSV）", type="csv", key="pm25_up")
    if pm25_file:
        df_pm25 = pd.read_csv(pm25_file)
        st.dataframe(df_pm25.head(), use_container_width=True)
        if st.button("保存PM2.5数据"):
            save_data(df_pm25, "china_pm25_upload", if_exists="replace")
            st.success(f"已保存 {len(df_pm25)} 条PM2.5记录。")

    st.divider()

    # ── Step 4: 手动上传健康/死亡数据 ──────────────────────────────────────
    st.subheader("Step 4 — 上传健康死亡数据（可选）")

    with st.expander("📥 卫生统计年鉴下载说明"):
        st.markdown("""
        **数据来源：** 国家卫生健康统计年鉴（National Health Statistical Yearbook）

        **下载地址：** `http://www.nhc.gov.cn/wjw/tjnj/list.shtml`

        **需要指标：**
        - 各省粗死亡率（‰）
        - 居民主要疾病死因（呼吸系统疾病死亡率）

        按下方模板整理后上传：
        """)
        tpl2 = get_health_template().to_csv(index=False).encode("utf-8-sig")
        st.download_button("下载健康数据填写模板", data=tpl2,
                           file_name="health_template.csv", mime="text/csv")

    health_file = st.file_uploader("上传健康数据（CSV）", type="csv", key="health_up")
    if health_file:
        df_health = pd.read_csv(health_file)
        st.dataframe(df_health.head(), use_container_width=True)
        if st.button("保存健康数据"):
            save_data(df_health, "china_health_upload", if_exists="replace")
            st.success(f"已保存 {len(df_health)} 条健康数据记录。")

    st.divider()

    # ── Step 5: 构建省级面板数据集 ────────────────────────────────────────
    st.subheader("Step 5 — 构建省级面板数据集")
    has_nbs = table_exists("raw_china_nbs")

    if st.button("构建中国省级面板", type="primary",
                 use_container_width=False, disabled=not has_nbs):
        with st.spinner("正在合并数据…"):
            panel = build_china_panel()
        if not panel.empty:
            st.success(f"面板数据集构建完成！共 {len(panel):,} 个省份-年份观测值。")
        else:
            st.error("构建失败，请先完成Step 1的NBS数据采集。")

    if table_exists("china_panel"):
        cp = load_data("china_panel")
        if not cp.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("观测值", f"{len(cp):,}")
            c2.metric("省份数", cp["province"].nunique())
            c3.metric("年份范围", f"{int(cp['year'].min())}–{int(cp['year'].max())}")
            with st.expander("预览数据（前30行）"):
                st.dataframe(cp.head(30), use_container_width=True, hide_index=True)
            csv = cp.to_csv(index=False).encode("utf-8-sig")
            st.download_button("导出省级面板数据（CSV）", data=csv,
                               file_name="china_provincial_panel.csv", mime="text/csv")


# ════════════════════════════════════════════════════════════════════════════
# Tab 2: 省级看板
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if not table_exists("china_panel"):
        st.info("请先完成Tab1的数据采集并构建面板数据集。")
        st.stop()

    cp = load_data("china_panel")
    if cp.empty:
        st.info("面板数据为空。")
        st.stop()

    numeric_cols = cp.select_dtypes(include="number").columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in ["year"]]

    VAR_ZH = {
        "gdp_bn_cny":        "GDP（亿元）",
        "gdp_per_capita_cny":"人均GDP（元）",
        "urbanization":      "城镇化率（%）",
        "population_10k":    "人口（万人）",
        "coal_prod_10kt":    "煤炭产量（万吨）",
        "oil_prod_10kt":     "石油产量（万吨）",
        "gas_prod_bcm":      "天然气产量（亿m³）",
        "energy_prod_10kt":  "能源总产量（万吨标煤）",
        "resource_intensity":"资源强度（能源产量/GDP）",
        "so2_emissions_10kt":"SO2排放（万吨）",
        "nox_emissions_10kt":"NOx排放（万吨）",
        "dust_emissions_10kt":"烟尘排放（万吨）",
        "aqi_mean":          "AQI年均值",
        "pm25_aqi":          "PM2.5年均值（μg/m³）",
        "pm25_annual":       "PM2.5卫星数据（μg/m³）",
        "crude_death_rate":  "粗死亡率（‰）",
        "airpol_death_rate": "大气污染死亡率（1/10万）",
        "ln_gdp_pc_cny":     "ln(人均GDP)",
        "coal_per_capita":   "人均煤炭产量",
    }

    def fmtz(v):
        return VAR_ZH.get(v, v)

    subtab1, subtab2, subtab3 = st.tabs(["📊 省级条形图", "📈 趋势图", "🔵 散点图"])

    with subtab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            bar_var = st.selectbox("展示变量", numeric_cols, format_func=fmtz, key="bar_var")
        with col2:
            years_avail = sorted(cp["year"].dropna().unique().astype(int))
            bar_year = st.selectbox("年份", years_avail[::-1], key="bar_year")
        with col3:
            bar_top = st.slider("显示省份数", 5, 31, 31, key="bar_top")

        df_bar = (cp[cp["year"] == bar_year][["province", bar_var]]
                  .dropna().sort_values(bar_var, ascending=False).head(bar_top))
        if not df_bar.empty:
            fig = px.bar(df_bar, x=bar_var, y="province", orientation="h",
                         color=bar_var, color_continuous_scale="Blues",
                         title=f"{bar_year}年 {fmtz(bar_var)} — 各省排名",
                         labels={bar_var: fmtz(bar_var), "province": "省份"})
            fig.update_layout(height=600, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with subtab2:
        col1, col2 = st.columns([1, 2])
        with col1:
            trend_var = st.selectbox("变量", numeric_cols, format_func=fmtz, key="trend_var_cn")
            default_provs = ["北京", "上海", "广东", "山西", "新疆", "陕西"]
            sel_provs = [p for p in default_provs if p in cp["province"].unique()]
            trend_provs = st.multiselect("选择省份", sorted(cp["province"].unique()),
                                         default=sel_provs, key="trend_provs")
        with col2:
            if trend_provs:
                df_trend = cp[cp["province"].isin(trend_provs)][
                    ["province", "year", trend_var]].dropna()
                fig = px.line(df_trend, x="year", y=trend_var, color="province",
                              title=f"{fmtz(trend_var)} 省级趋势",
                              labels={"year": "年份", trend_var: fmtz(trend_var)})
                fig.update_layout(height=420)
                st.plotly_chart(fig, use_container_width=True)

    with subtab3:
        col1, col2, col3 = st.columns(3)
        with col1:
            sc_x = st.selectbox("X轴", numeric_cols,
                                 index=numeric_cols.index("resource_intensity")
                                 if "resource_intensity" in numeric_cols else 0,
                                 format_func=fmtz, key="sc_x_cn")
        with col2:
            sc_y_opts = [v for v in numeric_cols if v != sc_x]
            sc_y = st.selectbox("Y轴", sc_y_opts,
                                 index=sc_y_opts.index("so2_emissions_10kt")
                                 if "so2_emissions_10kt" in sc_y_opts else 0,
                                 format_func=fmtz, key="sc_y_cn")
        with col3:
            sc_year = st.selectbox("年份（0=全期均值）",
                                   [0] + years_avail[::-1], key="sc_year_cn")

        if sc_year == 0:
            df_sc = cp.groupby("province")[[sc_x, sc_y]].mean().reset_index()
        else:
            df_sc = cp[cp["year"] == sc_year].copy()

        df_sc = df_sc.dropna(subset=[sc_x, sc_y])
        if not df_sc.empty:
            fig = px.scatter(df_sc, x=sc_x, y=sc_y, text="province",
                             trendline="ols",
                             title=f"{fmtz(sc_x)} vs {fmtz(sc_y)}",
                             labels={sc_x: fmtz(sc_x), sc_y: fmtz(sc_y)})
            fig.update_traces(textposition="top center")
            fig.update_layout(height=480)
            st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 3: 省级回归
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not table_exists("china_panel"):
        st.info("请先构建省级面板数据集。")
        st.stop()

    cp = load_data("china_panel")
    if cp.empty:
        st.stop()

    numeric_cols2 = [c for c in cp.select_dtypes(include="number").columns
                     if c != "year"]

    def fmtz2(v):
        return VAR_ZH.get(v, v)

    col1, col2 = st.columns(2)
    with col1:
        reg_y = st.selectbox("因变量 (Y)", numeric_cols2,
                              index=numeric_cols2.index("so2_emissions_10kt")
                              if "so2_emissions_10kt" in numeric_cols2 else 0,
                              format_func=fmtz2, key="cn_reg_y")
        reg_x_opts = [v for v in numeric_cols2 if v != reg_y]
        reg_x = st.multiselect("核心自变量（资源依赖）", reg_x_opts,
                               default=[v for v in ["resource_intensity", "coal_prod_10kt"]
                                        if v in reg_x_opts],
                               format_func=fmtz2, key="cn_reg_x")
        ctrl_opts = [v for v in reg_x_opts if v not in reg_x]
        reg_ctrl = st.multiselect("控制变量", ctrl_opts,
                                  default=[v for v in ["ln_gdp_pc_cny", "urbanization"]
                                           if v in ctrl_opts],
                                  format_func=fmtz2, key="cn_reg_ctrl")
    with col2:
        cn_entity_fe = st.checkbox("省份固定效应", value=True)
        cn_time_fe   = st.checkbox("年份固定效应", value=True)
        cn_cluster   = st.checkbox("聚类标准误（按省份）", value=True)

    if st.button("运行省级回归", type="primary"):
        all_x = reg_x + reg_ctrl
        if not all_x:
            st.warning("请选择自变量。")
        else:
            with st.spinner("计算中…"):
                res = run_panel_regression(
                    cp, reg_y, all_x,
                    entity_col="province", time_col="year",
                    entity_effects=cn_entity_fe,
                    time_effects=cn_time_fe,
                    cluster_entity=cn_cluster,
                )
            if "error" in res:
                st.error(res["error"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("观测值", res["n_obs"])
                c2.metric("省份数", res["n_entities"])
                c3.metric("组内R²", res["r2_within"])

                tbl = res["table"].copy()
                tbl["变量"] = tbl["变量"].apply(fmtz2)
                st.dataframe(tbl, use_container_width=True, hide_index=True)
                st.caption("*** p<0.01   ** p<0.05   * p<0.1")

                csv = tbl.to_csv(index=False).encode("utf-8-sig")
                st.download_button("导出结果（CSV）", data=csv,
                                   file_name="china_regression.csv", mime="text/csv")


# ════════════════════════════════════════════════════════════════════════════
# Tab 4: 数据说明
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("数据来源与变量说明")
    st.markdown("""
    ### 自动采集来源
    | 数据 | 来源 | 时间范围 | 层级 |
    |------|------|---------|------|
    | GDP、人口、城镇化率 | 国家统计局分省年度数据 | 2003–2022 | 省级 |
    | 能源/煤炭/石油/天然气产量 | 国家统计局 | 2003–2022 | 省级 |
    | 工业SO2、NOx、烟尘排放 | 国家统计局 | 2003–2022 | 省级 |
    | AQI、PM2.5（城市→省级均值） | 生态环境部/akshare | 2015–2022 | 城市→省 |

    ### 手动下载来源
    | 数据 | 来源 | 网址 |
    |------|------|------|
    | PM2.5卫星数据（高精度） | CHAP数据集 | weijing-rs.github.io/CHAP.html |
    | 死亡率/分病因死因 | 国家卫生健康统计年鉴 | nhc.gov.cn |

    ### 核心变量定义
    | 变量 | 定义 | 论文用途 |
    |------|------|---------|
    | `resource_intensity` | 能源产量/GDP | 资源依赖度（自变量） |
    | `coal_prod_10kt` | 煤炭产量万吨 | 资源依赖（稳健性） |
    | `so2_emissions_10kt` | SO2排放万吨 | 大气污染（因变量） |
    | `pm25_annual` | PM2.5年均μg/m³ | 大气清洁度（因变量） |
    | `ln_gdp_pc_cny` | ln(人均GDP) | 经济发展水平（控制） |
    | `urbanization` | 城镇化率% | 城市化（控制） |

    ### 与全球数据的整合方式
    中国省级分析可作为全球跨国回归的**补充分析**，在论文中以单独小节呈现：
    > *"As a complementary analysis, we use Chinese provincial panel data (31 provinces, 2003–2021)
    > to exploit within-country variation in resource dependence and atmospheric quality..."*
    """)
