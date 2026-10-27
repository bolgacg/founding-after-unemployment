"""Download every table this study uses into one folder.

Usage: python3 -I analysis/fetch.py raw

Statistics Denmark tables come from the StatBank API (POST https://api.statbank.dk/v1/data),
one CSV per table with codes rather than labels, plus the table's metadata (labels, last update).
The ILO generative AI exposure scores come from the authors' GitHub repository, pinned to the
commit that was current on the day of the fetch. A manifest records the date, the request bodies
and the commit, so the numbers on the page can be traced to a single download.
Standard library only.
"""
import datetime
import json
import os
import sys
import urllib.request

API = "https://api.statbank.dk/v1"
ILO_REPO = "pgmyrek/2025_GenAI_scores_ISCO08"
ILO_FILE = "Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx"

# One entry per table: the variables and values requested. Variables left out are eliminated by
# StatBank, which means it returns the total over them.
REQUESTS = {
    # New enterprises by municipality, 2007 to 2021 (discontinued table, still served).
    "DEMO9": {"REGI07A": ["*"], "MÆNGDE4": ["NYE", "AFU"], "Tid": ["*"]},
    # Its successor, 2019 onwards, used only to show the break between the two.
    "DEMO19": {"REGI07A": ["000"], "MÆNGDE4": ["NYE"], "Tid": ["*"]},
    # National new enterprises, old and new vintages, again only to show the break.
    "DEMO1": {"BRANCHEDB07127": ["TOT"], "FSTATUS": ["NYE"], "ENHED": ["NYE1"], "Tid": ["*"]},
    "DEMO11": {"BRANCHEDB07127": ["TOT"], "FSTATUS": ["NYE"], "ENHED": ["NYE1"], "Tid": ["*"]},
    # Long-term unemployed (gross unemployed 52 weeks or more), monthly, by municipality.
    "AULK04": {"OMRÅDE": ["*"], "ENHED": ["1", "2"], "ALDER": ["TOT"], "KØN": ["TOT"], "Tid": ["*"]},
    # All gross unemployed, seasonally adjusted, percent of the labour force, monthly.
    "AUS08": {"OMRÅDE": ["*"], "SAESONFAK": ["9"], "Tid": ["*"]},
    # Labour force by municipality of residence, end of November.
    "RAS400": {"OMRÅDE": ["*"], "ALDER": ["TOT"], "Tid": ["*"]},
    # Salaried employees by municipality of workplace, end of November.
    "RAS305": {"ARBEJDSSTED": ["*"], "ARBOMFANG": ["H", "D"], "Tid": ["*"]},
    # Quarterly moves between socio-economic statuses, from unemployment and from employee jobs.
    "FLOW1": {"TIDSOCIO": ["50", "15", "20", "25", "30", "35", "40"], "NYSOCIO": ["*"],
              "BEVÆGELSEV": ["*"], "ALDER": ["*"], "Tid": ["*"]},
    # Unemployment spells by duration, monthly.
    "AULK09": {"KMDR": ["*"], "ENHED": ["1", "4"], "YDELSESTYPE": ["TOT"], "KØN": ["TOT"], "Tid": ["*"]},
    # Full-time employees by occupation (DISCO-08), all sectors, all pay forms, both sexes.
    "LONS20": {"ARBF": ["*"], "SEKTOR": ["1000"], "AFLOEN": ["TIFA"], "LONGRP": ["LTOT"],
               "LØNMÅL": ["ANTAL"], "KØN": ["MOK"], "Tid": ["*"]},
}


def get(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": "founding-after-unemployment/1.0"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def main(out):
    os.makedirs(out, exist_ok=True)
    manifest = {"fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "statbank": {}, "ilo": {}}
    for table, variables in REQUESTS.items():
        info = json.loads(get(f"{API}/tableinfo/{table}?lang=en&format=JSON"))
        with open(os.path.join(out, f"{table}_info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=1)
        body = {"table": table, "format": "CSV", "lang": "en", "delimiter": "Semicolon",
                "valuePresentation": "Code",
                "variables": [{"code": k, "values": v} for k, v in variables.items()]}
        raw = get(f"{API}/data", body)
        with open(os.path.join(out, f"{table}.csv"), "wb") as f:
            f.write(raw)
        rows = raw.decode("utf-8-sig").count("\n")
        manifest["statbank"][table] = {"title": info.get("text"), "updated": info.get("updated"),
                                       "rows": rows, "request": body}
        print(f"{table}: {rows} rows, table updated {info.get('updated')}")

    commit = json.loads(get(f"https://api.github.com/repos/{ILO_REPO}/commits/main"))
    sha = commit["sha"]
    url = f"https://raw.githubusercontent.com/{ILO_REPO}/{sha}/{ILO_FILE}"
    blob = get(url)
    with open(os.path.join(out, "ilo_scores.xlsx"), "wb") as f:
        f.write(blob)
    manifest["ilo"] = {"repo": f"https://github.com/{ILO_REPO}", "commit": sha,
                       "commit_date": commit["commit"]["committer"]["date"], "file": ILO_FILE,
                       "url": url, "bytes": len(blob)}
    print(f"ILO scores: {len(blob)} bytes at commit {sha[:10]}")
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -I analysis/fetch.py RAW_DIR")
    main(sys.argv[1])
