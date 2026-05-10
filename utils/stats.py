import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.panel import PanelOLS, PooledOLS


# ── Descriptive statistics ────────────────────────────────────────────────────

def descriptive_stats(df: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    cols = [v for v in variables if v in df.columns]
    desc = df[cols].describe().T
    desc["missing"] = df[cols].isna().sum()
    desc["missing%"] = (desc["missing"] / len(df) * 100).round(1)
    desc = desc[["count", "mean", "std", "min", "25%", "50%", "75%", "max", "missing%"]]
    desc.columns = ["样本量", "均值", "标准差", "最小值", "25%", "中位数", "75%", "最大值", "缺失(%)"]
    return desc.round(3)


def correlation_matrix(df: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    cols = [v for v in variables if v in df.columns]
    return df[cols].corr().round(3)


# ── Panel regression ──────────────────────────────────────────────────────────

def run_panel_regression(
    df: pd.DataFrame,
    y_var: str,
    x_vars: list[str],
    entity_col: str = "country_code",
    time_col: str = "year",
    entity_effects: bool = True,
    time_effects: bool = True,
    cluster_entity: bool = True,
) -> dict:
    """
    Run panel OLS with fixed effects.
    Returns a dict with summary table and model stats.
    """
    needed = [entity_col, time_col, y_var] + x_vars
    sub = df[needed].dropna()

    if len(sub) < 30:
        return {"error": f"有效观测值仅 {len(sub)} 个，样本量不足，请检查变量覆盖率。"}

    sub = sub.set_index([entity_col, time_col])

    try:
        mod = PanelOLS(
            dependent=sub[y_var],
            exog=sm.add_constant(sub[x_vars]),
            entity_effects=entity_effects,
            time_effects=time_effects,
            drop_absorbed=True,
        )
        cov_type = "clustered" if cluster_entity else "robust"
        res = mod.fit(cov_type=cov_type, cluster_entity=cluster_entity)
    except Exception as e:
        return {"error": str(e)}

    # Build results table
    table = pd.DataFrame({
        "变量":   res.params.index,
        "系数":   res.params.values,
        "标准误": res.std_errors.values,
        "t统计量": res.tstats.values,
        "p值":    res.pvalues.values,
        "置信区间下限": res.conf_int()["lower"].values,
        "置信区间上限": res.conf_int()["upper"].values,
    }).round(4)

    table["显著性"] = table["p值"].apply(
        lambda p: "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.1 else ""))
    )

    return {
        "table":        table,
        "r2_within":    round(float(res.rsquared), 4),
        "r2_between":   round(float(getattr(res, "rsquared_between", np.nan)), 4),
        "n_obs":        int(res.nobs),
        "n_entities":   int(res.entity_info.total),
        "entity_effects": entity_effects,
        "time_effects":   time_effects,
        "summary_str":  str(res.summary),
    }


def run_pooled_ols(
    df: pd.DataFrame,
    y_var: str,
    x_vars: list[str],
    entity_col: str = "country_code",
    time_col: str = "year",
) -> dict:
    needed = [entity_col, time_col, y_var] + x_vars
    sub = df[needed].dropna().set_index([entity_col, time_col])

    if len(sub) < 30:
        return {"error": f"有效观测值仅 {len(sub)} 个，样本量不足。"}

    try:
        mod = PooledOLS(
            dependent=sub[y_var],
            exog=sm.add_constant(sub[x_vars]),
        )
        res = mod.fit(cov_type="robust")
    except Exception as e:
        return {"error": str(e)}

    table = pd.DataFrame({
        "变量":   res.params.index,
        "系数":   res.params.values,
        "标准误": res.std_errors.values,
        "t统计量": res.tstats.values,
        "p值":    res.pvalues.values,
    }).round(4)
    table["显著性"] = table["p值"].apply(
        lambda p: "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.1 else ""))
    )
    return {"table": table, "n_obs": int(res.nobs), "r2_within": round(float(res.rsquared), 4)}


# ── Mediation analysis (Sobel test) ──────────────────────────────────────────

def mediation_analysis(
    df: pd.DataFrame,
    treatment: str,
    mediator: str,
    outcome: str,
    controls: list[str],
    entity_col: str = "country_code",
    time_col: str = "year",
) -> dict:
    """Simple mediation: Baron-Kenny steps with panel FE."""

    # Step 1: treatment → outcome (total effect)
    res_c = run_panel_regression(df, outcome, [treatment] + controls,
                                  entity_col, time_col)
    # Step 2: treatment → mediator
    res_a = run_panel_regression(df, mediator, [treatment] + controls,
                                  entity_col, time_col)
    # Step 3: treatment + mediator → outcome (direct effect)
    res_b = run_panel_regression(df, outcome, [treatment, mediator] + controls,
                                  entity_col, time_col)

    if any("error" in r for r in [res_c, res_a, res_b]):
        errors = [r.get("error", "") for r in [res_c, res_a, res_b]]
        return {"error": "; ".join(e for e in errors if e)}

    def get_coef(res, var):
        row = res["table"][res["table"]["变量"] == var]
        if row.empty:
            return np.nan, np.nan
        return float(row["系数"].iloc[0]), float(row["标准误"].iloc[0])

    c, se_c   = get_coef(res_c, treatment)   # total effect
    a, se_a   = get_coef(res_a, treatment)   # treatment→mediator
    b, se_b   = get_coef(res_b, mediator)    # mediator→outcome (controlling treatment)
    c2, se_c2 = get_coef(res_b, treatment)   # direct effect

    indirect = a * b
    # Sobel SE
    sobel_se = np.sqrt(b**2 * se_a**2 + a**2 * se_b**2)
    sobel_z  = indirect / sobel_se if sobel_se > 0 else np.nan
    mediation_pct = (indirect / c * 100) if c != 0 else np.nan

    return {
        "total_effect":    round(c, 4),
        "direct_effect":   round(c2, 4),
        "indirect_effect": round(indirect, 4),
        "sobel_z":         round(sobel_z, 4),
        "sobel_p":         round(2 * (1 - float(sm.stats.normal_cdf(abs(sobel_z)))), 4),
        "mediation_pct":   round(mediation_pct, 1),
        "step1": res_c["table"],
        "step2": res_a["table"],
        "step3": res_b["table"],
    }
