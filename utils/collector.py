import wbgapi as wb
import pandas as pd
import requests
from utils.db import save_data, log_collection

# ── Indicator definitions ─────────────────────────────────────────────────────

INDICATOR_GROUPS = {
    "资源依赖（核心自变量）": {
        "NY.GDP.TOTL.RT.ZS": "总自然资源租金 (% GDP)",
        "NY.GDP.PETR.RT.ZS": "石油租金 (% GDP)",
        "NY.GDP.NGAS.RT.ZS": "天然气租金 (% GDP)",
        "NY.GDP.COAL.RT.ZS": "煤炭租金 (% GDP)",
        "NY.GDP.MINR.RT.ZS": "矿产租金 (% GDP)",
        "NY.GDP.FRST.RT.ZS": "森林租金 (% GDP)",
    },
    "大气环境（因变量）": {
        "EN.ATM.PM25.MC.M3": "PM2.5年均暴露 (μg/m³)",
        "EN.ATM.CO2E.PC":    "CO2排放 (人均吨)",
        "EN.ATM.METH.KT.CE": "甲烷排放 (kt CO2当量)",
    },
    "健康死亡（因变量）": {
        "SH.STA.AIRP.P5":    "大气污染死亡率 (per 100,000)",
        "SP.DYN.CDRT.IN":    "粗死亡率 (per 1,000)",
        "SH.DTH.NCOM.ZS":    "非传染病死亡占比 (%)",
    },
    "控制变量": {
        "NY.GDP.PCAP.PP.KD": "人均GDP-PPP (2017年不变价)",
        "SP.URB.TOTL.IN.ZS": "城镇化率 (%)",
        "NE.TRD.GNFS.ZS":    "贸易开放度 (% GDP)",
        "EG.USE.PCAP.KG.OE": "能源消耗 (kg油当量/人)",
        "EG.FEC.RNEW.ZS":    "可再生能源占比 (%)",
        "SP.POP.TOTL":       "总人口",
    },
    "机制变量（治理与产业）": {
        "CC.EST":            "腐败控制指数",
        "GE.EST":            "政府效能指数",
        "RL.EST":            "法治指数",
        "RQ.EST":            "监管质量指数",
        "NV.IND.MANF.ZS":   "制造业增加值 (% GDP)",
        "EG.ELC.COAL.ZS":   "煤电占比 (%)",
    },
}

# Flat lookup: code → Chinese name
ALL_INDICATORS: dict[str, str] = {}
for _grp in INDICATOR_GROUPS.values():
    ALL_INDICATORS.update(_grp)


# ── World Bank data fetch ─────────────────────────────────────────────────────

def fetch_one_indicator(code: str, name: str, start: int, end: int) -> pd.DataFrame:
    """Fetch a single WB indicator for all countries; return long-format DataFrame."""
    rows = []
    try:
        for item in wb.data.fetch(code, economy="all", time=range(start, end + 1)):
            if item["value"] is None:
                continue
            year_raw = item["time"]
            year = int(str(year_raw).replace("YR", ""))
            rows.append({
                "country_code":   str(item["economy"]),
                "year":           year,
                "indicator_code": code,
                "indicator_name": name,
                "value":          float(item["value"]),
            })
    except Exception as e:
        pass
    return pd.DataFrame(rows)


def fetch_world_bank(selected_groups: list[str], start: int, end: int,
                     progress_bar=None, status_text=None) -> int:
    """Fetch selected indicator groups and append to raw_wb_data table."""
    all_rows = []
    codes_to_fetch = []
    for grp in selected_groups:
        for code, name in INDICATOR_GROUPS[grp].items():
            codes_to_fetch.append((code, name))

    total = len(codes_to_fetch)
    for i, (code, name) in enumerate(codes_to_fetch):
        if status_text:
            status_text.text(f"正在获取 {name} ({i+1}/{total})…")
        df = fetch_one_indicator(code, name, start, end)
        all_rows.append(df)
        if progress_bar:
            progress_bar.progress((i + 1) / total)

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined = combined.dropna(subset=["value"])
        save_data(combined, "raw_wb_data", if_exists="append")
        log_collection("WorldBank", "success", len(combined))
        return len(combined)
    return 0


# ── Country metadata ──────────────────────────────────────────────────────────

def _extract(val):
    """Safely extract a label from a wbgapi field that may be dict, str, or None."""
    if isinstance(val, dict):
        return val.get("value", "") or val.get("id", "")
    return str(val) if val else ""


def fetch_country_metadata() -> pd.DataFrame:
    rows = []
    for eco in wb.economy.list():
        # wbgapi may return dict or SimpleNamespace depending on version
        if isinstance(eco, dict):
            code   = eco.get("id", "")
            name   = eco.get("value", "")
            income = _extract(eco.get("incomeLevel"))
            region = _extract(eco.get("region"))
        else:
            code   = getattr(eco, "id", "")
            name   = getattr(eco, "value", "")
            income = _extract(getattr(eco, "incomeLevel", None))
            region = _extract(getattr(eco, "region", None))
        rows.append({
            "country_code": code,
            "country_name": name,
            "income_level": income,
            "region":       region,
        })
    df = pd.DataFrame(rows)
    save_data(df, "country_metadata", if_exists="replace")
    log_collection("CountryMetadata", "success", len(df))
    return df


# ── WHO GHO mortality data ────────────────────────────────────────────────────

WHO_GHO_URL = "https://ghoapi.azureedge.net/api"

WHO_INDICATORS = {
    "SDGAIRBOD":   "室外空气污染死亡率 (per 100,000)",
    "SDGAIRBODH":  "室内空气污染死亡率 (per 100,000)",
}


def fetch_who_mortality(progress_bar=None, status_text=None) -> int:
    all_rows = []
    codes = list(WHO_INDICATORS.items())
    for i, (code, name) in enumerate(codes):
        if status_text:
            status_text.text(f"正在获取 WHO {name}…")
        try:
            url = f"{WHO_GHO_URL}/{code}"
            params = {"$filter": "SpatialDimType eq 'COUNTRY'", "$top": 10000}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("value", [])
            for rec in data:
                if rec.get("NumericValue") is None:
                    continue
                all_rows.append({
                    "country_code":   rec.get("SpatialDim", ""),
                    "year":           int(rec.get("TimeDim", 0)),
                    "indicator_code": code,
                    "indicator_name": name,
                    "value":          float(rec["NumericValue"]),
                    "sex":            rec.get("Dim1", "BTSX"),
                })
        except Exception as e:
            pass
        if progress_bar:
            progress_bar.progress((i + 1) / len(codes))

    if all_rows:
        df = pd.DataFrame(all_rows)
        save_data(df, "raw_who_data", if_exists="append")
        log_collection("WHO_GHO", "success", len(df))
        return len(df)
    return 0


# ── Build merged panel dataset ────────────────────────────────────────────────

def build_panel_dataset() -> pd.DataFrame:
    from utils.db import load_data

    raw = load_data("raw_wb_data")
    if raw.empty:
        return pd.DataFrame()

    # Remove duplicates before pivoting
    raw = raw.drop_duplicates(subset=["country_code", "year", "indicator_code"])

    panel = raw.pivot_table(
        index=["country_code", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    ).reset_index()
    panel.columns.name = None

    # Rename codes to short readable names
    rename = {
        "NY.GDP.TOTL.RT.ZS": "resource_rents",
        "NY.GDP.PETR.RT.ZS": "oil_rents",
        "NY.GDP.NGAS.RT.ZS": "gas_rents",
        "NY.GDP.COAL.RT.ZS": "coal_rents",
        "NY.GDP.MINR.RT.ZS": "mineral_rents",
        "NY.GDP.FRST.RT.ZS": "forest_rents",
        "EN.ATM.PM25.MC.M3": "pm25",
        "EN.ATM.CO2E.PC":    "co2_pc",
        "EN.ATM.METH.KT.CE": "methane",
        "SH.STA.AIRP.P5":    "airpol_mortality",
        "SP.DYN.CDRT.IN":    "death_rate",
        "SH.DTH.NCOM.ZS":    "ncd_death_share",
        "NY.GDP.PCAP.PP.KD": "gdp_pc_ppp",
        "SP.URB.TOTL.IN.ZS": "urbanization",
        "NE.TRD.GNFS.ZS":    "trade_gdp",
        "EG.USE.PCAP.KG.OE": "energy_use",
        "EG.FEC.RNEW.ZS":    "renewable_energy",
        "SP.POP.TOTL":       "population",
        "CC.EST":            "corruption_control",
        "GE.EST":            "govt_effectiveness",
        "RL.EST":            "rule_of_law",
        "RQ.EST":            "regulatory_quality",
        "NV.IND.MANF.ZS":   "manufacturing_share",
        "EG.ELC.COAL.ZS":   "coal_electricity",
    }
    panel = panel.rename(columns={k: v for k, v in rename.items() if k in panel.columns})

    # Merge metadata
    meta = load_data("country_metadata")
    if not meta.empty:
        panel = panel.merge(
            meta[["country_code", "country_name", "income_level", "region"]],
            on="country_code", how="left",
        )

    # Log GDP per capita
    if "gdp_pc_ppp" in panel.columns:
        import numpy as np
        panel["ln_gdp_pc"] = np.log(panel["gdp_pc_ppp"].replace(0, float("nan")))

    panel = panel.sort_values(["country_code", "year"]).reset_index(drop=True)
    save_data(panel, "panel_dataset", if_exists="replace")
    log_collection("PanelBuild", "success", len(panel))
    return panel
