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
        "crude_death_rate": [None] * 62,
        "airpol_death_rate": [None] * 62,
        "hospital_beds_per10k": [None] * 62,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 地级市（Prefecture-level city）数据
# ══════════════════════════════════════════════════════════════════════════════

# akshare 支持AQI查询的168个重点城市（含归属省份）
CITY_PROVINCE_MAP = {
    "北京":"北京","天津":"天津","石家庄":"河北","唐山":"河北","秦皇岛":"河北",
    "邯郸":"河北","邢台":"河北","保定":"河北","张家口":"河北","承德":"河北",
    "沧州":"河北","廊坊":"河北","太原":"山西","大同":"山西","阳泉":"山西",
    "长治":"山西","晋城":"山西","呼和浩特":"内蒙古","包头":"内蒙古","赤峰":"内蒙古",
    "沈阳":"辽宁","大连":"辽宁","鞍山":"辽宁","抚顺":"辽宁","本溪":"辽宁",
    "丹东":"辽宁","锦州":"辽宁","长春":"吉林","吉林市":"吉林","哈尔滨":"黑龙江",
    "齐齐哈尔":"黑龙江","大庆":"黑龙江","上海":"上海","南京":"江苏","无锡":"江苏",
    "徐州":"江苏","常州":"江苏","苏州":"江苏","南通":"江苏","连云港":"江苏",
    "淮安":"江苏","盐城":"江苏","扬州":"江苏","镇江":"江苏","泰州":"江苏",
    "宿迁":"江苏","杭州":"浙江","宁波":"浙江","温州":"浙江","嘉兴":"浙江",
    "湖州":"浙江","绍兴":"浙江","金华":"浙江","衢州":"浙江","舟山":"浙江",
    "台州":"浙江","丽水":"浙江","合肥":"安徽","芜湖":"安徽","蚌埠":"安徽",
    "淮南":"安徽","马鞍山":"安徽","淮北":"安徽","铜陵":"安徽","安庆":"安徽",
    "福州":"福建","厦门":"福建","莆田":"福建","三明":"福建","泉州":"福建",
    "漳州":"福建","南昌":"江西","景德镇":"江西","萍乡":"江西","九江":"江西",
    "济南":"山东","青岛":"山东","淄博":"山东","枣庄":"山东","东营":"山东",
    "烟台":"山东","潍坊":"山东","济宁":"山东","泰安":"山东","威海":"山东",
    "郑州":"河南","开封":"河南","洛阳":"河南","平顶山":"河南","安阳":"河南",
    "鹤壁":"河南","新乡":"河南","焦作":"河南","濮阳":"河南","武汉":"湖北",
    "黄石":"湖北","十堰":"湖北","宜昌":"湖北","襄阳":"湖北","长沙":"湖南",
    "株洲":"湖南","湘潭":"湖南","衡阳":"湖南","广州":"广东","深圳":"广东",
    "珠海":"广东","汕头":"广东","佛山":"广东","韶关":"广东","湛江":"广东",
    "东莞":"广东","中山":"广东","南宁":"广西","柳州":"广西","桂林":"广西",
    "海口":"海南","三亚":"海南","重庆":"重庆","成都":"四川","自贡":"四川",
    "攀枝花":"四川","泸州":"四川","德阳":"四川","绵阳":"四川","贵阳":"贵州",
    "遵义":"贵州","昆明":"云南","曲靖":"云南","拉萨":"西藏","西安":"陕西",
    "铜川":"陕西","宝鸡":"陕西","咸阳":"陕西","渭南":"陕西","延安":"陕西",
    "兰州":"甘肃","嘉峪关":"甘肃","金昌":"甘肃","西宁":"青海","银川":"宁夏",
    "石嘴山":"宁夏","吴忠":"宁夏","乌鲁木齐":"新疆","克拉玛依":"新疆",
}
ALL_CITIES = list(CITY_PROVINCE_MAP.keys())


def fetch_city_aqi(start_year: int = 2015, end_year: int = 2022,
                   progress_bar=None, status_text=None) -> int:
    """
    Fetch city-level AQI from akshare (keep city granularity, not aggregated).
    """
    all_rows = []
    total = len(ALL_CITIES)

    for i, city in enumerate(ALL_CITIES):
        if status_text:
            status_text.text(f"采集AQI：{city} ({i+1}/{total})…")
        try:
            df_c = ak.air_quality_hist(
                city=city,
                start_year=str(start_year),
                end_year=str(end_year),
            )
            if df_c.empty:
                continue
            df_c.columns = [c.strip() for c in df_c.columns]
            date_col = df_c.columns[0]
            df_c[date_col] = pd.to_datetime(df_c[date_col], errors="coerce")
            df_c = df_c.dropna(subset=[date_col])
            df_c["year"] = df_c[date_col].dt.year

            aqi_col  = next((c for c in df_c.columns if "AQI"  in c.upper()), None)
            pm25_col = next((c for c in df_c.columns if "PM2.5" in c.upper() or "pm25" in c.lower()), None)
            pm10_col = next((c for c in df_c.columns if "PM10" in c.upper()), None)
            so2_col  = next((c for c in df_c.columns if "SO2"  in c.upper()), None)
            no2_col  = next((c for c in df_c.columns if "NO2"  in c.upper()), None)
            o3_col   = next((c for c in df_c.columns if "O3"   in c.upper() and "8H" not in c.upper()), None)

            for yr, grp in df_c.groupby("year"):
                row = {
                    "city":     city,
                    "province": CITY_PROVINCE_MAP.get(city, ""),
                    "year":     int(yr),
                    "obs_days": len(grp),
                }
                for col, key in [(aqi_col,"aqi"),(pm25_col,"pm25"),(pm10_col,"pm10"),
                                  (so2_col,"so2"),(no2_col,"no2"),(o3_col,"o3")]:
                    if col:
                        row[key] = round(float(grp[col].mean()), 2)
                all_rows.append(row)
            time.sleep(0.3)
        except Exception:
            continue

        if progress_bar:
            progress_bar.progress((i + 1) / total)

    if all_rows:
        df = pd.DataFrame(all_rows)
        save_data(df, "raw_city_aqi", if_exists="append")
        log_collection("CityAQI", "success", len(df))
        return len(df)
    return 0


def get_city_nbs_template() -> pd.DataFrame:
    """NBS城市经济数据上传模板（用户从统计局网站手动下载后填入）"""
    sample_cities = ["北京", "上海", "广州", "深圳", "重庆",
                     "成都", "武汉", "西安", "郑州", "杭州"]
    rows = []
    for city in sample_cities:
        for yr in [2019, 2020]:
            rows.append({
                "city": city,
                "province": CITY_PROVINCE_MAP.get(city, ""),
                "year": yr,
                "gdp_bn_cny": None,           # GDP（亿元）
                "gdp_per_capita_cny": None,   # 人均GDP（元）
                "population_10k": None,       # 年末人口（万人）
                "urbanization": None,         # 城镇化率（%）
                "industry_va_bn": None,       # 工业增加值（亿元）
                "so2_ton": None,              # SO2排放量（吨）
                "smoke_dust_ton": None,       # 烟尘排放量（吨）
                "energy_consumption": None,   # 能源消耗（万吨标煤）
            })
    return pd.DataFrame(rows)


def get_city_resource_template() -> pd.DataFrame:
    """城市资源依赖数据模板"""
    sample_cities = ["北京", "上海", "广州", "大庆", "鄂尔多斯"]
    rows = []
    for city in sample_cities:
        for yr in [2019, 2020]:
            rows.append({
                "city": city,
                "province": CITY_PROVINCE_MAP.get(city, ""),
                "year": yr,
                "mining_output_bn": None,      # 采矿业产值（亿元）
                "coal_prod_10kt": None,        # 煤炭产量（万吨）
                "oil_prod_10kt": None,         # 石油产量（万吨）
                "gas_prod_bcm": None,          # 天然气产量（亿立方米）
                "resource_tax_mn": None,       # 资源税（百万元）
            })
    return pd.DataFrame(rows)


def build_city_panel() -> pd.DataFrame:
    """Merge city AQI + uploaded NBS + resource data into city panel."""
    from utils.db import load_data

    frames = []

    aqi = load_data("raw_city_aqi")
    if not aqi.empty:
        aqi = aqi.drop_duplicates(subset=["city", "year"])
        frames.append(aqi)

    nbs_city = load_data("city_nbs_upload")
    if not nbs_city.empty:
        nbs_city = nbs_city.drop_duplicates(subset=["city", "year"])
        if frames:
            frames[0] = frames[0].merge(nbs_city, on=["city", "year"], how="left",
                                        suffixes=("", "_nbs"))
        else:
            frames.append(nbs_city)

    res_city = load_data("city_resource_upload")
    if not res_city.empty:
        res_city = res_city.drop_duplicates(subset=["city", "year"])
        if frames:
            frames[0] = frames[0].merge(res_city, on=["city", "year"], how="left",
                                        suffixes=("", "_res"))
        else:
            frames.append(res_city)

    pm25_city = load_data("city_pm25_upload")
    if not pm25_city.empty and frames:
        frames[0] = frames[0].merge(pm25_city, on=["city", "year"], how="left",
                                    suffixes=("", "_chap"))

    if not frames:
        return pd.DataFrame()

    panel = frames[0].sort_values(["city", "year"]).reset_index(drop=True)

    # 构建关键指标
    if "gdp_bn_cny" in panel.columns and "mining_output_bn" in panel.columns:
        panel["mining_share"] = (
            panel["mining_output_bn"] / panel["gdp_bn_cny"].replace(0, np.nan) * 100
        )
    if "gdp_per_capita_cny" in panel.columns:
        panel["ln_gdp_pc"] = np.log(panel["gdp_per_capita_cny"].replace(0, np.nan))

    save_data(panel, "city_panel", if_exists="replace")
    log_collection("CityPanelBuild", "success", len(panel))
    return panel


# ══════════════════════════════════════════════════════════════════════════════
# 县级数据（County-level）
# ══════════════════════════════════════════════════════════════════════════════

def get_county_pm25_template() -> pd.DataFrame:
    """CHAP县级PM2.5数据上传模板"""
    sample = [
        ("110101", "东城区", "北京", "北京"),
        ("110102", "西城区", "北京", "北京"),
        ("120101", "和平区", "天津", "天津"),
        ("130102", "长安区", "石家庄", "河北"),
        ("440103", "荔湾区", "广州",  "广东"),
    ]
    rows = []
    for code, county, city, prov in sample:
        for yr in [2019, 2020]:
            rows.append({
                "county_code":   code,   # 6位行政区划代码
                "county_name":   county,
                "city":          city,
                "province":      prov,
                "year":          yr,
                "pm25_annual":   None,   # 年均PM2.5 μg/m³（CHAP数据集）
                "pm25_max":      None,   # 年最大月均值
            })
    return pd.DataFrame(rows)


def get_county_economic_template() -> pd.DataFrame:
    """县级经济/资源数据上传模板（来自《中国县域统计年鉴》）"""
    sample = [
        ("110101","东城区","北京","北京"),
        ("110102","西城区","北京","北京"),
        ("440103","荔湾区","广州","广东"),
    ]
    rows = []
    for code, county, city, prov in sample:
        for yr in [2019, 2020]:
            rows.append({
                "county_code":        code,
                "county_name":        county,
                "city":               city,
                "province":           prov,
                "year":               yr,
                "gdp_bn_cny":         None,  # GDP（亿元）
                "gdp_per_capita_cny": None,  # 人均GDP（元）
                "population_10k":     None,  # 人口（万人）
                "industry_share":     None,  # 工业占比（%）
                "mining_output_bn":   None,  # 采矿业产值（亿元）
                "fiscal_revenue_mn":  None,  # 财政收入（百万元）
            })
    return pd.DataFrame(rows)


def build_county_panel() -> pd.DataFrame:
    """Merge county PM2.5 + economic data into county panel."""
    from utils.db import load_data

    pm25 = load_data("county_pm25_upload")
    eco  = load_data("county_economic_upload")

    if pm25.empty and eco.empty:
        return pd.DataFrame()

    if pm25.empty:
        panel = eco
    elif eco.empty:
        panel = pm25
    else:
        key = ["county_code", "year"] if "county_code" in pm25.columns else ["county_name", "year"]
        panel = pm25.merge(eco, on=key, how="outer", suffixes=("", "_eco"))

    # 构建资源依赖指标
    if "mining_output_bn" in panel.columns and "gdp_bn_cny" in panel.columns:
        panel["mining_share"] = (
            panel["mining_output_bn"] / panel["gdp_bn_cny"].replace(0, np.nan) * 100
        )
    if "gdp_per_capita_cny" in panel.columns:
        panel["ln_gdp_pc"] = np.log(panel["gdp_per_capita_cny"].replace(0, np.nan))

    panel = panel.sort_values(
        ["county_code" if "county_code" in panel.columns else "county_name", "year"]
    ).reset_index(drop=True)

    save_data(panel, "county_panel", if_exists="replace")
    log_collection("CountyPanelBuild", "success", len(panel))
    return panel
