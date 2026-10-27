"""Write index.html from the page template and results.json.

Usage: python3 -I analysis/render.py analysis/page.html data/results.json index.html

Every number in the page text is a {{key}} placeholder filled here from results.json, and the chart
data is embedded as one JSON object, so the page cannot drift from the analysis. The script stops
if the template asks for a key that is not computed, or if a computed key is never used.
Standard library only.
"""
import datetime
import json
import re
import sys

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
STATBANK = "https://www.statbank.dk/{}"


def num(x, d=2):
    """Fixed decimals with a true minus sign."""
    s = f"{x:,.{d}f}"
    if s.startswith("-"):
        s = "−" + s[1:]
    if s in ("−0." + "0" * d,):
        s = "0." + "0" * d
    return s


def whole(n):
    return f"{int(round(n)):,}"


def month(code):
    y, m = code.split("M")
    return f"{MONTHS[int(m) - 1]} {y}"


def day(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def age(label):
    return label.replace(" years", "").replace("-", " to ")


def keys(r):
    p1, p2, p3, br, man = r["p1"], r["p2"], r["p3"], r["breaks"], r["manifest"]
    lad = {s["key"]: s for s in p1["ladder"]}
    spec = {s["key"]: s for s in p1["specs"]}
    fe = spec["main"]
    k = {
        "fetched": day(man["fetched_at_utc"]),
        "n_munis": str(p1["n_munis"]), "n_obs": whole(p1["n_obs"]),
        "first": str(p1["first"]), "last": str(p1["last"]),
        "fe_b": num(fe["b"]), "fe_lo": num(fe["lo"]), "fe_hi": num(fe["hi"]), "between_abs1": num(abs(lad["between"]["b"]), 1),
        "pooled_b": num(lad["pooled"]["b"]),
        "mean_rate": num(p1["mean_rate"], 1),
        "n_years": str(p1["last"] - p1["first"] + 1),
        "entity_b": num(lad["entity_only"]["b"]),
        "ltu_nat_2009": num(p1["ltu_nat_2009"], 1), "ltu_nat_2011": num(p1["ltu_nat_2011"], 1),
        "left_unemp": whole(p2["cond"]["unemployed"]["left_share"]), "left_emp": num(p2["cond"]["employee"]["left_share"], 1),
        "cond_unemp": num(p2["cond"]["unemployed"]["self_among_left"], 1), "cond_emp": num(p2["cond"]["employee"]["self_among_left"], 1),
        "u2020_to_self": whole(p2["u2020_to_self"]), "u2020_base": whole(p2["u2020_base"]),
        "later_base_max": whole(p2["later_base_max"]),
        "staff_2009": whole(p1["staff_new_2009"]), "births_2009": whole(p1["births_2009"]),
        "lag_b": num(spec["lag"]["b"]), "lag_lo": num(spec["lag"]["lo"]), "lag_hi": num(spec["lag"]["hi"]),
        "flow_years": f"{p2['years'][0]} to {p2['years'][-1]}",
        "rate_unemp": num(p2["rate_unemp"]), "rate_emp": num(p2["rate_emp"]), "ratio": num(p2["ratio"], 1),
        "flow_last_year": p2["last_year"], "from_unemp_last": whole(p2["from_unemp_last"]),
        "from_emp_last": whole(p2["from_emp_last"]),
        "peak_age": age(p2["peak_age"]), "peak_rate": num(p2["peak_rate"]),
        "rate_unemp_2020": num(p2["by_year"]["2020_unemployed"]["rate"]),
        "benchmark": num(p2["benchmark"]), "unr_b": num(p2["unr_b"]), "unr_lo": num(p2["unr_lo"]), "unr_hi": num(p2["unr_hi"]),
        "zero_cells": str(p2["zero_cells"]),
        "spells_start": month(p2["spells"]["months"][0]), "last_month": month(p2["last_month"]), "last52": whole(p2["last52"]),
        "peak52_month": month(p2["peak52_month"]), "peak52": whole(p2["peak52"]),
        "n_ilo": str(p3["n_ilo"]), "n_disco": str(p3["n_disco"]), "n_matched": str(p3["n_matched"]),
        "cover_last": whole(100 * p3["cover_last"]), "exp_first": p3["first"], "exp_last": p3["last"],
        "high_first": num(p3["high"][p3["first"]], 1), "high_last": num(p3["high"][p3["last"]], 1),
        "high_2022": num(p3["high"]["2022"], 1),
        "r_after": num(p3["after"]["r"]), "r_before": num(p3["before"]["r"]), "n_after": str(p3["after"]["n"]),
        "rw_after": num(p3["after"]["r_weighted"]), "rw_before": num(p3["before"]["r_weighted"]),
        "rs_after": num(p3["after"]["r_spearman"]),
        "demo_old_2019": whole(br["demo1_2019"]), "demo_new_2019": whole(br["demo11_2019"]),
        "ilo_commit": man["ilo"]["commit"][:7], "ilo_commit_url": f"{man['ilo']['repo']}/tree/{man['ilo']['commit']}",
    }
    assert br["demo9_2019"] == br["demo1_2019"] and br["demo19_2019"] == br["demo11_2019"]
    edu = {u["code"]: u for u in p3["unmatched"]}
    k["edu_2343"] = whole(edu["2343"]["emp_last"])
    k["edu_2357"] = whole(edu["2357"]["emp_last"])
    k["spec_rows"] = spec_rows(p1["specs"])
    k["source_rows"] = source_rows(man)
    return k


def spec_rows(specs):
    rows = []
    for s in specs:
        cls = ' class="ref"' if s["key"] == "main" else ""
        rows.append(f'<tr{cls}><td data-k="Specification">{s["label"]}</td><td class="n" data-k="Estimate">{num(s["b"])}</td>'
                    f'<td class="n" data-k="95 percent interval">{num(s["lo"])} to {num(s["hi"])}</td>'
                    f'<td class="n" data-k="Years">{s["years"]}</td><td class="n" data-k="Observations">{whole(s["n"])}</td></tr>')
    return "\n".join(rows)


TABLES = [
    ("DEMO9", "New enterprises by municipality, 2007 to 2021 (discontinued, old series)"),
    ("DEMO19", "New enterprises by municipality, 2019 onwards (new series)"),
    ("DEMO1", "New enterprises by industry, 2001 to 2021 (discontinued, old series)"),
    ("DEMO11", "New enterprises by industry, 2019 onwards (new series)"),
    ("AULK04", "Long term unemployed by municipality, monthly"),
    ("AUS08", "Gross unemployed in full time equivalents, seasonally adjusted, by municipality, monthly"),
    ("RAS400", "Labour force used for unemployment rates, by municipality, end of November"),
    ("RAS305", "Salaried employees by municipality of workplace, end of November"),
    ("FLOW1", "Quarterly changes in socio economic status"),
    ("AULK09", "Unemployment spells by duration, monthly"),
    ("LONS20", "Earnings and number of full time employees by occupation (DISCO-08)"),
]


def source_rows(man):
    out = []
    for tid, text in TABLES:
        upd = man["updated"][tid]
        out.append(f'<li><a href="{STATBANK.format(tid)}">{tid}</a>: {text}. Last updated by Statistics Denmark on '
                   f'{day(upd)}.</li>')
    return "\n".join(out)


def chart_data(r):
    p1, p2, p3 = r["p1"], r["p2"], r["p3"]
    keep = ("2013", "2022", p3["last"])
    return {
        "p1": {"ladder": [{k: s[k] for k in ("key", "label", "b", "lo", "hi", "n")} for s in p1["ladder"]],
               "points": p1["points"], "names": p1["names"], "mean_x": p1["mean_ltu"], "mean_y": p1["mean_rate"],
               "pooled_b": next(s["b"] for s in p1["ladder"] if s["key"] == "pooled"),
               "fe_b": next(s["b"] for s in p1["ladder"] if s["key"] == "twoway"),
               "first": p1["first"], "last": p1["last"]},
        "p2": {"ages": [age(a) for a in p2["ages"]], "series": p2["series"], "years": p2["years"],
               "spells": p2["spells"]},
        "p3": {"points": p3["points"], "grads": p3["grads"], "comp": {y: p3["comp"][y] for y in keep},
               "high": {y: p3["high"][y] for y in keep}, "after": p3["after"], "before": p3["before"],
               "top": p3["top_exposed"]["code"], "last": p3["last"]},
    }


def main(template, results, out):
    r = json.load(open(results, encoding="utf-8"))
    page = open(template, encoding="utf-8").read()
    k = keys(r)
    wanted = set(re.findall(r"\{\{(\w+)\}\}", page))
    missing = wanted - set(k)
    unused = set(k) - wanted
    if missing:
        sys.exit(f"template asks for keys that are not computed: {sorted(missing)}")
    if unused:
        sys.exit(f"computed keys never used on the page: {sorted(unused)}")
    page = re.sub(r"\{\{(\w+)\}\}", lambda m: k[m.group(1)], page)
    data = json.dumps(chart_data(r), ensure_ascii=False, separators=(",", ":"))
    assert "</" not in data
    page = page.replace("/*DATA*/null", data)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {out}: {len(page):,} bytes, {len(wanted)} numbers filled")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python3 -I analysis/render.py TEMPLATE RESULTS_JSON OUT_HTML")
    main(*sys.argv[1:])
