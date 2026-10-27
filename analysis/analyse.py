"""Compute every number and chart series on the page from the downloaded tables.

Usage: python -I analysis/analyse.py RAW_DIR DATA_DIR

Reads the folder written by fetch.py, writes derived CSV files and results.json into DATA_DIR.
render.py then fills the page from results.json, so no number on the page is typed by hand.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from linearmodels.panel import PanelOLS

FIRST, LAST = 2009, 2021          # years where DEMO9 and AULK04 overlap
FLOW_YEARS = ["2021", "2022", "2023", "2024"]   # 2020 is shown but left out of pooled rates (lockdowns)


def read(raw, table):
    df = pd.read_csv(os.path.join(raw, f"{table}.csv"), sep=";", dtype=str, encoding="utf-8-sig")
    df["v"] = pd.to_numeric(df["INDHOLD"], errors="coerce")
    return df


def labels(raw, table, var):
    info = json.load(open(os.path.join(raw, f"{table}_info.json"), encoding="utf-8"))
    for v in info["variables"]:
        if v["id"] == var:
            return {x["id"]: x["text"] for x in v["values"]}
    raise KeyError(var)


def est(res, x):
    ci = res.conf_int().loc[x]
    return {"b": float(res.params[x]), "lo": float(ci.iloc[0]), "hi": float(ci.iloc[1]),
            "p": float(res.pvalues[x]), "n": int(res.nobs)}


# ---------------------------------------------------------------- panel 1: municipalities
def municipalities(raw, out):
    d9 = read(raw, "DEMO9").rename(columns={"REGI07A": "m", "TID": "t"})
    births = d9[d9["MÆNGDE4"] == "NYE"][["m", "t", "v"]].rename(columns={"v": "births"})
    staff = d9[d9["MÆNGDE4"] == "AFU"][["m", "t", "v"]].rename(columns={"v": "staff_new"})
    a4 = read(raw, "AULK04").rename(columns={"OMRÅDE": "m"})
    a4["t"] = a4["TID"].str[:4]
    ltu = a4[a4["ENHED"] == "2"].groupby(["m", "t"])["v"].agg(["mean", "count"]).reset_index()
    ltu = ltu.rename(columns={"mean": "ltu", "count": "ltu_months"})
    a8 = read(raw, "AUS08").rename(columns={"OMRÅDE": "m"})
    a8["t"] = a8["TID"].str[:4]
    unr = a8.groupby(["m", "t"])["v"].mean().rename("unr").reset_index()
    lf = read(raw, "RAS400").rename(columns={"OMRÅDE": "m", "TID": "t", "v": "lf"})[["m", "t", "lf"]]
    r5 = read(raw, "RAS305")
    emp = r5.groupby(["ARBEJDSSTED", "TID"])["v"].sum().rename("emp").reset_index()
    emp = emp.rename(columns={"ARBEJDSSTED": "m", "TID": "t"})

    df = births.merge(staff, on=["m", "t"], how="left")
    for other in (ltu, unr, lf, emp):
        df = df.merge(other, on=["m", "t"], how="left")
    df["t"] = df["t"].astype(int)
    df = df.sort_values(["m", "t"])
    for c in ("ltu", "unr"):
        df[c + "_lag"] = df.groupby("m")[c].shift(1)
    df["rate"] = 1000 * df["births"] / df["lf"]
    df["rate_emp"] = 1000 * df["births"] / df["emp"]

    nat = df[df["m"] == "000"].set_index("t")
    p = df[(df["m"] != "000") & df["t"].between(FIRST, LAST)].copy()
    assert p["ltu_months"].eq(12).all(), "a municipality-year lacks twelve months of AULK04"
    names = labels(raw, "DEMO9", "REGI07A")
    p["name"] = p["m"].map(names)
    n_m = p["m"].nunique()
    assert len(p) == n_m * (LAST - FIRST + 1), "panel is not balanced"

    pi = p.set_index(["m", "t"])

    def fe(y, x, data=pi, weights=None, entity=True, time=True):
        d = data[[y, x] + ([weights] if weights else [])].dropna()
        mod = PanelOLS(d[y], d[[x]], entity_effects=entity, time_effects=time,
                       weights=d[weights] if weights else None)
        return est(mod.fit(cov_type="clustered", cluster_entity=True), x)

    main = fe("rate", "ltu")
    specs = [
        {"key": "main", "label": "Main estimate: long term unemployment, same year", "years": f"{FIRST} to {LAST}", **main},
        {"key": "lag", "label": "Long term unemployment of the year before", "years": f"{FIRST + 1} to {LAST}", **fe("rate", "ltu_lag")},
        {"key": "unr", "label": "All gross unemployment in full time equivalents (AUS08)", "years": f"{FIRST} to {LAST}", **fe("rate", "unr")},
        {"key": "unr_lag", "label": "All gross unemployment in full time equivalents, year before", "years": f"{FIRST} to {LAST}", **fe("rate", "unr_lag")},
        {"key": "emp", "label": "New firms per 1,000 salaried employees working in the municipality (RAS305)", "years": f"{FIRST} to {LAST}", **fe("rate_emp", "ltu")},
        {"key": "weighted", "label": "Municipalities weighted by their labour force", "years": f"{FIRST} to {LAST}", **fe("rate", "ltu", weights="lf")},
        {"key": "nocovid", "label": "Leaving out 2020 and 2021", "years": f"{FIRST} to 2019",
         **fe("rate", "ltu", data=pi[pi.index.get_level_values("t") <= 2019])},
    ]
    pooled = smf.ols("rate ~ ltu", data=p).fit(cov_type="cluster", cov_kwds={"groups": p["m"]})
    between_df = p.groupby("m")[["rate", "ltu"]].mean()
    between = smf.ols("rate ~ ltu", data=between_df).fit(cov_type="HC1")
    ladder = [
        {"key": "between", "label": f"Comparing municipalities with each other (each one's {LAST - FIRST + 1} year average)", **est(between, "ltu")},
        {"key": "pooled", "label": f"All {len(p):,} municipality years in one pool", **est(pooled, "ltu")},
        {"key": "time_only", "label": "Pool, net of each year's national swing (year effects only)", **fe("rate", "ltu", entity=False)},
        {"key": "entity_only", "label": "Same municipality over time (municipality effects only)", **fe("rate", "ltu", time=False)},
        {"key": "twoway", "label": "Same municipality over time, net of each year's national swing", **main},
    ]

    # Two-way demeaned values for the "within" view of the chart, with the grand means added back
    # so the axes keep their units. In a balanced panel the slope of rate_w on ltu_w equals the
    # two-way fixed effects coefficient (Frisch, Waugh and Lovell); the assert checks that.
    for c in ("ltu", "rate"):
        g = p[c].mean()
        p[c + "_w"] = p[c] - p.groupby("m")[c].transform("mean") - p.groupby("t")[c].transform("mean") + 2 * g
    xw, yw = p["ltu_w"] - p["ltu_w"].mean(), p["rate_w"] - p["rate_w"].mean()
    fwl = float((xw * yw).sum() / (xw ** 2).sum())
    assert abs(fwl - main["b"]) < 1e-9, (fwl, main["b"])
    within_sd = float((p["ltu"] - p.groupby("m")["ltu"].transform("mean")).std())

    # The DEMO9 column called "employees" counts staff of the new enterprises themselves.
    staff_share = float(nat.loc[2009, "staff_new"] / nat.loc[2009, "births"])

    cols = ["m", "name", "t", "births", "lf", "emp", "ltu", "unr", "rate", "rate_emp", "ltu_w", "rate_w"]
    p[cols].to_csv(os.path.join(out, "municipality_panel.csv"), index=False, float_format="%.6g")
    spec_df = pd.DataFrame(ladder + specs)
    spec_df.to_csv(os.path.join(out, "panel_estimates.csv"), index=False, float_format="%.6g")

    national = []
    for t in range(FIRST, LAST + 1):
        national.append({"t": t, "births": int(nat.loc[t, "births"]), "lf": int(nat.loc[t, "lf"]),
                         "rate": float(1000 * nat.loc[t, "births"] / nat.loc[t, "lf"]), "ltu": float(nat.loc[t, "ltu"])})
    points = [{"m": r.m, "t": int(r.t), "x": round(r.ltu, 4), "y": round(r.rate, 3),
               "xw": round(r.ltu_w, 4), "yw": round(r.rate_w, 3)} for r in p.itertuples()]
    return {
        "n_munis": int(n_m), "n_obs": int(len(p)), "first": FIRST, "last": LAST,
        "mean_rate": float(p["rate"].mean()), "mean_ltu": float(p["ltu"].mean()),
        "within_sd_ltu": within_sd, "ladder": ladder, "specs": specs,
        "names": {m: names[m] for m in sorted(p["m"].unique())}, "points": points, "national": national,
        "staff_new_2009": int(nat.loc[2009, "staff_new"]), "births_2009": int(nat.loc[2009, "births"]),
        "staff_per_birth_2009": staff_share,
        "ltu_nat_2009": float(nat.loc[2009, "ltu"]), "ltu_nat_2011": float(nat.loc[2011, "ltu"]),
        "births_nat_2008": int(nat.loc[2008, "births"]), "births_nat_2009": int(nat.loc[2009, "births"]),
    }


def breaks(raw):
    d1 = read(raw, "DEMO1").set_index("TID")["v"]
    d11 = read(raw, "DEMO11").set_index("TID")["v"]
    d19 = read(raw, "DEMO19").set_index("TID")["v"]
    d9 = read(raw, "DEMO9")
    d9n = d9[(d9["REGI07A"] == "000") & (d9["MÆNGDE4"] == "NYE")].set_index("TID")["v"]
    return {"demo1_2019": int(d1["2019"]), "demo11_2019": int(d11["2019"]),
            "demo9_2019": int(d9n["2019"]), "demo19_2019": int(d19["2019"]),
            "demo11_last_year": d11.index.max(), "demo11_last": int(d11[d11.index.max()])}


# ---------------------------------------------------------------- panel 2: flows and spells
def flows(raw, out, ladder_unr):
    f = read(raw, "FLOW1")
    f = f[~f["ALDER"].isin(["-16", "OV69"])].copy()          # ages 16 to 69, as in the chart
    f["from"] = np.where(f["TIDSOCIO"] == "50", "unemployed", "employee")
    employee_codes = {"15", "20", "25", "30", "35", "40"}
    # "Leaving" means leaving unemployment, or leaving employee work altogether.
    f["left"] = np.where(f["from"] == "unemployed", f["NYSOCIO"] != "50", ~f["NYSOCIO"].isin(employee_codes))
    f["to_self"] = np.where(f["NYSOCIO"] == "06", f["v"], 0.0)
    zero_cells = int(((f["NYSOCIO"] == "06") & (f["TIDSOCIO"] == "50") & (f["v"] == 0)).sum())
    pooled_years = f[f["TID"].isin(FLOW_YEARS)]
    cond = {}
    for frm in ("unemployed", "employee"):
        g = pooled_years[pooled_years["from"] == frm]
        left = g.loc[g["left"], "v"].sum()
        cond[frm] = {"left_share": float(100 * left / g["v"].sum()), "self_among_left": float(100 * g["to_self"].sum() / left)}
    by_age = f.groupby(["from", "ALDER", "TID"]).agg(to_self=("to_self", "sum"), base=("v", "sum")).reset_index()
    by_age = by_age[~by_age["ALDER"].isin(["-16", "OV69"])]
    by_age["rate"] = 100 * by_age["to_self"] / by_age["base"]
    by_age.to_csv(os.path.join(out, "flow_to_self_employment_by_age.csv"), index=False, float_format="%.6g")
    by_year = f.groupby(["from", "TID"]).agg(to_self=("to_self", "sum"), base=("v", "sum")).reset_index()
    by_year["rate"] = 100 * by_year["to_self"] / by_year["base"]
    by_year.to_csv(os.path.join(out, "flow_to_self_employment_by_year.csv"), index=False, float_format="%.6g")

    def pooled(frm):
        s = by_year[(by_year["from"] == frm) & by_year["TID"].isin(FLOW_YEARS)]
        return float(100 * s["to_self"].sum() / s["base"].sum())
    u, e = pooled("unemployed"), pooled("employee")
    yr = {r.TID + "_" + r._1: {"to_self": int(r.to_self), "base": int(r.base), "rate": float(r.rate)}
          for r in by_year.rename(columns={"from": "_1"}).itertuples()}
    last = max(by_year["TID"])
    from_unemp_last = int(by_year[(by_year["from"] == "unemployed") & (by_year["TID"] == last)]["to_self"].iloc[0])
    from_emp_last = int(by_year[(by_year["from"] == "employee") & (by_year["TID"] == last)]["to_self"].iloc[0])
    age_labels = labels(raw, "FLOW1", "ALDER")
    ages = [a for a in age_labels if a not in ("-16", "OV69")]
    series = {}
    for frm in ("unemployed", "employee"):
        for t in sorted(by_age["TID"].unique()):
            s = by_age[(by_age["from"] == frm) & (by_age["TID"] == t)].set_index("ALDER")
            series[f"{frm}_{t}"] = [{"age": a, "rate": float(s.loc[a, "rate"]), "n": int(s.loc[a, "to_self"]),
                                     "base": int(s.loc[a, "base"])} for a in ages]
        s = by_age[(by_age["from"] == frm) & by_age["TID"].isin(FLOW_YEARS)].groupby("ALDER")[["to_self", "base"]].sum()
        series[f"{frm}_pooled"] = [{"age": a, "rate": float(100 * s.loc[a, "to_self"] / s.loc[a, "base"]),
                                    "n": int(s.loc[a, "to_self"]), "base": int(s.loc[a, "base"])} for a in ages]
    peak = max(series["unemployed_pooled"], key=lambda r: r["rate"])
    u20 = by_year[(by_year["from"] == "unemployed") & (by_year["TID"] == "2020")].iloc[0]
    later = by_year[(by_year["from"] == "unemployed") & by_year["TID"].isin(["2022", "2023", "2024"])]
    assert u20["to_self"] > later["to_self"].max(), "2020 entries are not above every year from 2022 to 2024"
    # A rough scale for the panel: one more point of unemployment is ten more unemployed people per
    # 1,000 in the labour force. If each of them moved into self-employment at the unemployed rate
    # instead of the employee rate, for four quarters, the extra entries per 1,000 would be:
    benchmark = 10 * 4 * (u - e) / 100

    a9 = read(raw, "AULK09")
    cnt = a9[a9["ENHED"] == "1"].pivot_table(index="TID", columns="KMDR", values="v")
    pct = a9[a9["ENHED"] == "4"].pivot_table(index="TID", columns="KMDR", values="v")
    cnt.to_csv(os.path.join(out, "unemployment_spells_by_duration.csv"), float_format="%.0f")
    months = list(cnt.index)
    spells = {"months": months, "durations": [int(k) for k in cnt.columns],
              "count": {str(int(k)): [None if pd.isna(v) else int(v) for v in cnt[k]] for k in cnt.columns},
              "pct": {str(int(k)): [None if pd.isna(v) else float(v) for v in pct[k].reindex(months)] for k in pct.columns}}
    first_full = {str(int(k)): cnt[k].first_valid_index() for k in cnt.columns}
    peak52 = cnt["052"].idxmax()
    lastm = months[-1]
    return {
        "years": FLOW_YEARS, "rate_unemp": u, "rate_emp": e, "ratio": u / e, "zero_cells": zero_cells,
        "by_year": yr, "last_year": last, "from_unemp_last": from_unemp_last, "from_emp_last": from_emp_last,
        "share_from_unemp_last": 100 * from_unemp_last / (from_unemp_last + from_emp_last),
        "ages": [age_labels[a] for a in ages], "series": series, "peak_age": age_labels[peak["age"]], "cond": cond,
        "u2020_to_self": int(u20["to_self"]), "u2020_base": int(u20["base"]),
        "later_base_min": int(later["base"].min()), "later_base_max": int(later["base"].max()),
        "peak_rate": peak["rate"], "benchmark": benchmark,
        "unr_b": ladder_unr["b"], "unr_lo": ladder_unr["lo"], "unr_hi": ladder_unr["hi"],
        "spells": spells, "spell_first": first_full, "peak52_month": peak52, "peak52": int(cnt.loc[peak52, "052"]),
        "last_month": lastm, "last52": int(cnt.loc[lastm, "052"]), "last26": int(cnt.loc[lastm, "026"]),
        "last104": int(cnt.loc[lastm, "104"]), "last52_pct": float(pct.loc[lastm, "052"]),
        "peak52_pct": float(pct.loc[peak52, "052"]),
    }


# ---------------------------------------------------------------- panel 3: AI exposure
GRADS = ["Not Exposed", "Minimal Exposure", "Exposed: Gradient 1", "Exposed: Gradient 2",
         "Exposed: Gradient 3", "Exposed: Gradient 4"]


def exposure(raw, out):
    ilo = pd.read_excel(os.path.join(raw, "ilo_scores.xlsx"), dtype={"ISCO_08": str})
    ilo["ISCO_08"] = ilo["ISCO_08"].str.strip().str.zfill(4)
    occ = ilo.groupby("ISCO_08").agg(ilo_title=("Title", "first"), score=("mean_score_2025", "first"),
                                     sd=("SD_2025", "first"), gradient=("potential25", "first"),
                                     tasks=("taskID", "count")).reset_index()
    assert occ.groupby("ISCO_08").size().max() == 1
    lons = read(raw, "LONS20")
    disco = labels(raw, "LONS20", "ARBF")
    l4 = lons[lons["ARBF"].str.fullmatch(r"\d{4}")]
    wide = l4.pivot_table(index="ARBF", columns="TID", values="v")
    years = list(wide.columns)
    m = wide.join(occ.set_index("ISCO_08"), how="left")
    m["title"] = [disco[c][5:] for c in m.index]
    matched = m[m["score"].notna()]
    unmatched = [{"code": c, "title": disco[c][5:], "emp_last": None if pd.isna(m.loc[c, years[-1]]) else int(m.loc[c, years[-1]])}
                 for c in m.index if pd.isna(m.loc[c, "score"])]
    cover = {y: float(matched[y].sum() / wide[y].sum()) for y in years}
    comp = {}
    for y in years:
        s = matched[y].dropna()
        g = matched.loc[s.index].groupby("gradient")[y].sum() / s.sum()
        comp[y] = {k: float(100 * g.get(k, 0.0)) for k in GRADS}
        comp[y]["wmean"] = float((matched.loc[s.index, "score"] * s).sum() / s.sum())
    high = {y: comp[y]["Exposed: Gradient 3"] + comp[y]["Exposed: Gradient 4"] for y in years}

    def change(y0, y1, min_emp=500):
        d = matched[[y0, y1, "score", "title", "gradient"]].dropna(subset=[y0, y1])
        d = d[d[y0] >= min_emp].copy()
        d["chg"] = 100 * ((d[y1] / matched[y1].sum()) / (d[y0] / matched[y0].sum()) - 1)
        r = float(np.corrcoef(d["score"], d["chg"])[0, 1])
        w = d[y0]
        mx, my = np.average(d["score"], weights=w), np.average(d["chg"], weights=w)
        rw = float(np.average((d["score"] - mx) * (d["chg"] - my), weights=w) /
                   np.sqrt(np.average((d["score"] - mx) ** 2, weights=w) * np.average((d["chg"] - my) ** 2, weights=w)))
        rs = float(d["score"].rank().corr(d["chg"].rank()))
        return d, {"n": int(len(d)), "r": r, "r_weighted": rw, "r_spearman": rs}

    after, after_stats = change("2022", years[-1])
    before, before_stats = change("2019", "2022")
    occ_out = m.reset_index().rename(columns={"ARBF": "disco"})
    occ_out = occ_out[["disco", "title", "ilo_title", "score", "sd", "gradient", "tasks"] + years]
    occ_out.to_csv(os.path.join(out, "occupations_exposure_employment.csv"), index=False, float_format="%.6g")

    pts = []
    for code in matched.index:
        row = matched.loc[code]
        pt = {"c": code, "n": row["title"], "s": round(float(row["score"]), 3), "g": GRADS.index(row["gradient"])}
        for key, d in (("a", after), ("b", before)):
            if code in d.index:
                pt[key] = round(float(d.loc[code, "chg"]), 2)
        pt["e22"] = None if pd.isna(row["2022"]) else int(row["2022"])
        pt["e19"] = None if pd.isna(row["2019"]) else int(row["2019"])
        pt["e25"] = None if pd.isna(row[years[-1]]) else int(row[years[-1]])
        if "a" in pt or "b" in pt:
            pts.append(pt)
    big_exposed = matched[matched["gradient"].isin(GRADS[4:])].sort_values(years[-1], ascending=False)
    top = big_exposed.index[0]
    return {
        "years": years, "first": years[0], "last": years[-1], "n_ilo": int(len(occ)),
        "n_disco": int(len(wide)), "n_matched": int(len(matched)), "unmatched": unmatched,
        "cover_first": cover[years[0]], "cover_last": cover[years[-1]], "comp": comp, "high": high,
        "after": after_stats, "before": before_stats, "points": pts, "grads": GRADS,
        "top_exposed": {"code": top, "title": matched.loc[top, "title"], "score": float(matched.loc[top, "score"]),
                        "emp_last": int(matched.loc[top, years[-1]]), "emp_2022": int(matched.loc[top, "2022"])},
        "tot_last": int(wide[years[-1]].sum()),
    }


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    manifest = json.load(open(os.path.join(raw, "manifest.json"), encoding="utf-8"))
    p1 = municipalities(raw, out)
    unr = next(s for s in p1["specs"] if s["key"] == "unr")
    res = {"manifest": {"fetched_at_utc": manifest["fetched_at_utc"],
                        "updated": {k: v["updated"] for k, v in manifest["statbank"].items()},
                        "ilo": manifest["ilo"]},
           "p1": p1, "breaks": breaks(raw), "p2": flows(raw, out, unr), "p3": exposure(raw, out)}
    with open(os.path.join(out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
    main_est = p1["specs"][0]
    print(f"two-way FE: {main_est['b']:.3f} [{main_est['lo']:.3f}, {main_est['hi']:.3f}] n={main_est['n']} munis={p1['n_munis']}")
    for s in p1["ladder"] + p1["specs"]:
        print(f"  {s['key']:12s} {s['b']:7.3f} [{s['lo']:7.3f}, {s['hi']:7.3f}] p={s['p']:.3f} n={s['n']}")
    p2 = res["p2"]
    print(f"flows {p2['years'][0]}..{p2['years'][-1]}: unemployed {p2['rate_unemp']:.3f}% employees {p2['rate_emp']:.3f}% ratio {p2['ratio']:.2f} benchmark {p2['benchmark']:.3f}")
    p3 = res["p3"]
    print(f"exposure: high share {p3['high'][p3['first']]:.2f}% ({p3['first']}) {p3['high'][p3['last']]:.2f}% ({p3['last']}); r after {p3['after']} before {p3['before']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -I analysis/analyse.py RAW_DIR DATA_DIR")
    main(sys.argv[1], sys.argv[2])
