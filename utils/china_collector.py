"""
中国省级面板数据采集模块
数据来源：
  1. 国家统计局API (NBS) — 经济/资源指标
  2. akshare — 城市AQI历史数据（汇总至省级）
  3. CSV手动上传 — PM2.5/死亡/卫生统计
"""

import json
import time
import requests
import pandas as pd
import numpy as np
import akshare as ak
from utils.db import save_data, log_collection

# ── 省份定义 ──────────────────────────────────────────────────────────────────

PROVINCE_CODE = {
    "北京": "110000", "天津": "120000", "河北": "130000",
    "山西": "140000", "内蒙古": "150000", "辽宁": "210000",
    "吉林": "220000", "黑龙江": "230000", "上海": "310000",
    "江苏": "320000", "浙江": "330000", "安徽": "340000",
    "福建": "350000", "江西": "360000", "山东": "370000",
    "河南": "410000", "湖北": "420000", "湖南": "430000",
    "广东": "440000", "广西": "450000", "海南": "460000",
    "重庆": "500000", "四川": "510000", "贵州": "520000",
    "云南": "530000", "西藏": "540000", "陕西": "610000",
    "甘肃": "620000", "青海": "630000", "宁夏": "640000",
    "新疆": "650000",
}
CODE_PROVINCE = {v: k for k, v in PROVINCE_CODE.items()}
PROVINCES_31 = list(PROVINCE_CODE.keys())

# 各省代表城市（用于AQI汇总）
PROVINCE_CITIES = {
    "北京": ["北京"], "天津": ["天津"],
    "河北": ["石家庄", "保定", "唐山", "邯郸", "邢台"],
    "山西": ["太原", "大同", "长治"],
    "内蒙古": ["呼和浩特", "包头", "赤峰"],
    "辽宁": ["沈阳", "大连", "鞍山", "抚顺"],
    "吉林": ["长春", "吉林市"],
    "黑龙江": ["哈尔滨", "齐齐哈尔", "大庆"],
    "上海": ["上海"], "江苏": ["南京", "苏州", "无锡", "南通"],
    "浙江": ["杭州", "宁波", "温州"],
    "安徽": ["合肥", "芜湖", "蚌埠"],
    "福建": ["福州", "厦门", "泉州"],
    "江西": ["南昌", "赣州", "九江"],
    "山东": ["济南", "青岛", "烟台", "淄博"],
    "河南": ["郑州", "洛阳", "开封", "南阳"],
    "湖北": ["武汉", "宜昌", "襄阳"],
    "湖南": ["长沙", "株洲", "衡阳"],
    "广东": ["广州", "深圳", "东莞", "佛山"],
    "广西": ["南宁", "桂林", "柳州"],
    "海南": ["海口", "三亚"],
    "重庆": ["重庆"], "四川": ["成都", "绵阳", "德阳"],
    "贵州": ["贵阳", "遵义"],
    "云南": ["昆明", "曲靖"],
    "西藏": ["拉萨"], "陕西": ["西安", "宝鸡", "咸阳"],
    "甘肃": ["兰州", "天水"],
    "青海": ["西宁"], "宁夏": ["银川"],
    "新疆": ["乌鲁木齐", "克拉玛依"],
}

# ── NBS 指标定义 ───────────────────────────────────────────────────────────────

NBS_INDICATORS = {
    "经济基础": {
        "A020E": "地区生产总值(亿元)",
        "A020F": "人均地区生产总值(元)",
        "A0301": "年末常住人口(万人)",
        "A0601": "城镇化率(%)",
        "A060101": "城镇人口(万人)",
    },
    "资源与工业（核心自变量）": {
        "B020":   "工业增加值(亿元)",
        "E0103":  "能源生产总量(万吨标准煤)",
        "E010301": "原煤产量(万吨)",
        "E010302": "原油产量(万吨)",
        "E010303": "天然气产量(亿立方米)",
        "H020101": "工业废气排放量(亿标立方米)",
    },
    "环境排放（因变量辅助）": {
        "H07040": "工业二氧化硫排放量(万吨)",
        "H07050": "工业氮氧化物排放量(万吨)",
        "H07060": "工业烟(粉)尘排放量(万吨)",
    },
}
ALL_NBS: dict[str, str] = {}
for g in NBS_INDICATORS.values():
    ALL_NBS.update(g)

# ── NBS API 采集 ──────────────────────────────────────────────────────────────

NBS_URL = "https://data.stats.gov.cn/easyquery.htm"
NBS_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://data.stats.gov.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _nbs_fetch_one(indicator_code: str, years: list[int]) -> list[dict]:
    """Fetch one NBS indicator for all provinces."""
    year_str = ",".join(str(y) for y in years)
    params = {
        "m": "QueryData",
        "dbcode": "fsnd",
        "rowcode": "reg",
        "colcode": "sj",
        "wds": json.dumps([{"wdcode": "zb", "valuecode": indicator_code}]),
        "dfwds": json.dumps([{"wdcode": "sj", "valuecode": year_str}]),
        "k1": str(int(time.time() * 1000)),
    }
    try:
        r = requests.get(NBS_URL, params=params, headers=NBS_HEADERS, timeout=30)
        data = r.json()
        rows = []
        nodes = data.get("returndata", {}).get("datanodes", [])
        for node in nodes:
            val_info = node.get("data", {})
            if val_info.get("strdata") in ("", None) and val_info.get("data") is None:
                continue
            raw_val = val_info.get("data") or val_info.get("strdata")
            if raw_val is None:
                continue
            # code format: "indicatorCode,regCode,year"
            code_parts = node.get("code", "").split(",")
            if len(code_parts) < 3:
                continue
            reg_code = code_parts[1]
            year = int(code_parts[2])
            prov = CODE_PROVINCE.get(reg_code)
            if prov is None:
                continue
            rows.append({
                "province": prov,
                "province_code": reg_code,
                "year": year,
                "indicator_code": indicator_code,
                "indicator_name": ALL_NBS.get(indicator_code, indicator_code),
                "value": float(raw_val),
            })
        return rows
    except Exception:
        return []


def fetch_nbs_data(selected_groups: list[str], start: int, end: int,
                   progress_bar=None, status_text=None) -> int:
    """Fetch selected NBS indicator groups for all provinces."""
    codes_to_fetch = []
    for grp in selected_groups:
        for code, name in NBS_INDICATORS[grp].items():
            codes_to_fetch.append((code, name))

    all_rows = []
    years = list(range(start, end + 1))
    total = len(codes_to_fetch)

    for i, (code, name) in enumerate(codes_to_fetch):
        if status_text:
            status_text.text(f"正在获取：{name} ({i+1}/{total})…")
        rows = _nbs_fetch_one(code, years)
        all_rows.extend(rows)
        time.sleep(0.5)  # 礼貌性延迟，避免被封
        if progress_bar:
            progress_bar.progress((i + 1) / total)

    if all_rows:
        df = pd.DataFrame(all_rows)
        save_data(df, "raw_china_nbs", if_exists="append")
        log_collection("NBS_Provincial", "success", len(df))
        return len(df)
    return 0


# ── akshare AQI 采集（城市→省级汇总）────────────────────────────────────────

def fetch_china_aqi(start_year: int = 2015, end_year: int = 2022,
                    progress_bar=None, status_text=None) -> int:
    """
    Fetch city AQI via akshare, aggregate to province level (annual mean).
    Data available from 2014 onwards for ~168 key cities.
    """
    all_rows = []
    prov_list = list(PROVINCE_CITIES.items())
    total = len(prov_list)

    for i, (prov, cities) in enumerate(prov_list):
        if status_text:
            status_text.text(f"采集AQI：{prov} ({i+1}/{total})…")
        prov_records = []
        for city in cities:
            try:
                df_city = ak.air_quality_hist(
                    city=city,
                    start_year=str(start_year),
                    end_year=str(end_year),
                )
                if df_city.empty:
                    continue
                # 统一列名
                df_city.columns = [c.strip() for c in df_city.columns]
                if "date" not in df_city.columns and df_city.columns[0] != "date":
                    df_city = df_city.rename(columns={df_city.columns[0]: "date"})
                df_city["date"] = pd.to_datetime(df_city["date"], errors="coerce")
                df_city = df_city.dropna(subset=["date"])
                df_city["year"] = df_city["date"].dt.year

                # AQI列
                aqi_col = next((c for c in df_city.columns
                                if "AQI" in c.upper() or "aqi" in c.lower()), None)
                pm25_col = next((c for c in df_city.columns
                                 if "PM2.5" in c.upper() or "pm25" in c.lower()), None)

                for yr, grp in df_city.groupby("year"):
                    rec = {"city": city, "province": prov, "year": int(yr)}
                    if aqi_col:
                        rec["aqi"] = grp[aqi_col].mean()
                    if pm25_col:
                        rec["pm25_city"] = grp[pm25_col].mean()
                    prov_records.append(rec)
                time.sleep(0.3)
            except Exception:
                continue

        # 聚合到省级：省内城市均值
        if prov_records:
            df_prov = pd.DataFrame(prov_records)
            for yr, grp in df_prov.groupby("year"):
                row = {"province": prov, "year": int(yr), "city_count": len(grp["city"].unique())}
                if "aqi" in grp.columns:
                    row["aqi_mean"] = round(grp["aqi"].mean(), 2)
                if "pm25_city" in grp.columns:
                    row["pm25_aqi"] = round(grp["pm25_city"].mean(), 2)
                all_rows.append(row)

        if progress_bar:
            progress_bar.progress((i + 1) / total)

    if all_rows:
        df = pd.DataFrame(all_rows)
        save_data(df, "raw_china_aqi", if_exists="append")
        log_collection("AQI_Provincial", "success", len(df))
        return len(df)
    return 0


# ── 构建中国省级面板数据集 ────────────────────────────────────────────────────

def build_china_panel() -> pd.DataFrame:
    """Merge NBS + AQI + uploaded data into provincial panel."""
    from utils.db import load_data

    frames = []

    # NBS经济/资源数据
    nbs_raw = load_data("raw_china_nbs")
    if not nbs_raw.empty:
        nbs_wide = nbs_raw.drop_duplicates(
            subset=["province", "year", "indicator_code"]
        ).pivot_table(
            index=["province", "province_code", "year"],
            columns="indicator_code",
            values="value",
            aggfunc="first",
        ).reset_index()
        nbs_wide.columns.name = None

        rename = {
            "A020E": "gdp_bn_cny",
            "A020F": "gdp_per_capita_cny",
            "A0301": "population_10k",
            "A0601": "urbanization",
            "B020":  "industry_va_bn",
            "E0103": "energy_prod_10kt",
            "E010301": "coal_prod_10kt",
            "E010302": "oil_prod_10kt",
            "E010303": "gas_prod_bcm",
            "H020101": "industrial_gas_100m3",
            "H07040": "so2_emissions_10kt",
            "H07050": "nox_emissions_10kt",
            "H07060": "dust_emissions_10kt",
        }
        nbs_wide = nbs_wide.rename(
            columns={k: v for k, v in rename.items() if k in nbs_wide.columns}
        )

        # 构建资源依赖指标
        if "energy_prod_10kt" in nbs_wide.columns and "gdp_bn_cny" in nbs_wide.columns:
            nbs_wide["resource_intensity"] = (
                nbs_wide["energy_prod_10kt"] / nbs_wide["gdp_bn_cny"].replace(0, np.nan)
            )
        if "coal_prod_10kt" in nbs_wide.columns and "population_10k" in nbs_wide.columns:
            nbs_wide["coal_per_capita"] = (
                nbs_wide["coal_prod_10kt"] / nbs_wide["population_10k"].replace(0, np.nan)
            )
        if "gdp_per_capita_cny" in nbs_wide.columns:
            nbs_wide["ln_gdp_pc_cny"] = np.log(
                nbs_wide["gdp_per_capita_cny"].replace(0, np.nan)
            )

        frames.append(nbs_wide)

    # AQI数据
    aqi_raw = load_data("raw_china_aqi")
    if not aqi_raw.empty:
        aqi_raw = aqi_raw.drop_duplicates(subset=["province", "year"])
        if frames:
            frames[0] = frames[0].merge(
                aqi_raw[["province", "year", "aqi_mean", "pm25_aqi"]],
                on=["province", "year"], how="left",
            )
        else:
            frames.append(aqi_raw)

    # 手动上传的PM2.5数据
    pm25_upload = load_data("china_pm25_upload")
    if not pm25_upload.empty and frames:
        frames[0] = frames[0].merge(
            pm25_upload, on=["province", "year"], how="left",
        )

    # 手动上传的健康/死亡数据
    health_upload = load_data("china_health_upload")
    if not health_upload.empty and frames:
        frames[0] = frames[0].merge(
            health_upload, on=["province", "year"], how="left",
        )

    if not frames:
        return pd.DataFrame()

    panel = frames[0].sort_values(["province", "year"]).reset_index(drop=True)
    save_data(panel, "china_panel", if_exists="replace")
    log_collection("ChinaPanelBuild", "success", len(panel))
    return panel


# ── CSV 上传模板 ──────────────────────────────────────────────────────────────

def get_pm25_template() -> pd.DataFrame:
    return pd.DataFrame({
        "province": PROVINCES_31 * 2,
        "year": [2019] * 31 + [2020] * 31,
        "pm25_annual": [None] * 62,          # 年均PM2.5 μg/m³（来自CHAP或官方数据）
        "pm25_days_exceed": [None] * 62,     # 超标天数
    })


def get_health_template() -> pd.DataFrame:
    return pd.DataFrame({
        "province": PROVINCES_31 * 2,
        "year": [2019] * 31 + [2020] * 31,
        "crude_death_rate": [None] * 62,     # 粗死亡率（‰）
        "airpol_death_rate": [None] * 62,    # 大气污染死亡率（1/10万）
        "hospital_beds_per10k": [None] * 62, # 每万人医疗床位数
    })
