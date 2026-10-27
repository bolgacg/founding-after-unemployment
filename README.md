# When unemployment rises in Denmark, do more people start firms?

Live page: https://bolgacg.github.io/founding-after-unemployment/

This repository asks how far free public data go on one question: when Danish unemployment rises, do more people start firms, and is generative AI exposure changing the jobs they leave? I wrote it as a work sample for the DTU Entrepreneurship PhD position in Entrepreneurship, AI, and Labor Market Disruption.

The short answer is that the public aggregates cannot tell. Across Denmark's 98 municipalities from 2009 to 2021, places with more long term unemployment had fewer new firms, but within a municipality over time the link is close to zero in a two way fixed effects panel. Person by person, the unemployed move into self employment far more often than employees. The tables that would join the two (who founded, from which job, after how long a spell) exist only in the registers.

## How to rerun it

```
python3 -m venv .venv && .venv/bin/pip install -r analysis/requirements.txt
python3 -I analysis/fetch.py raw
.venv/bin/python -I analysis/analyse.py raw data
python3 -I analysis/render.py analysis/page.html data/results.json index.html
```

`fetch.py` downloads eleven Statistics Denmark tables through the StatBank API and the ILO exposure scores from the authors' GitHub repository, pinned to the commit of the day, and writes a manifest with the date. It uses only the Python standard library. `analyse.py` computes every number and writes the CSV files in `data/` plus `data/results.json`. `render.py` writes those numbers into `index.html` and stops if the page text asks for a number that is not computed. The raw downloads go into `raw/`, which is not committed; a rerun on a later day fetches revised data, so some numbers may move.

## What is in `data/`

- `municipality_panel.csv`: one row per municipality and year, 2009 to 2021, with new enterprises, labour force, long term unemployment and the demeaned values used in the chart.
- `panel_estimates.csv`: every regression on the page, with estimate, 95 percent interval, p value and observations.
- `flow_to_self_employment_by_age.csv` and `flow_to_self_employment_by_year.csv`: moves into self employment from unemployment and from employee jobs (FLOW1).
- `unemployment_spells_by_duration.csv`: monthly counts of spells of 26 to 156 weeks (AULK09).
- `occupations_exposure_employment.csv`: each DISCO-08 occupation with its ILO exposure score and group and its full time employees, 2013 to 2025 (LONS20).

## Sources and licences

- Statistics Denmark, StatBank tables DEMO9, DEMO19, DEMO1, DEMO11, AULK04, AUS08, RAS400, RAS305, FLOW1, AULK09 and LONS20, read through https://api.statbank.dk/v1. Statistics Denmark allows reuse of its published data with the source named.
- Gmyrek, P., Berg, J., Kamiński, K., Konopczyński, F., Ładna, A., Nafradi, B., Rosłaniec, K. and Troszyński, M. (2025). Generative AI and Jobs: A Refined Global Index of Occupational Exposure. ILO Working Paper 140. Scores from https://github.com/pgmyrek/2025_GenAI_scores_ISCO08 under CC BY 4.0. The derived occupation file in `data/` keeps the occupation mean score and exposure group unchanged.
- Nikiforou, A., Dencker, J. C. and Gruber, M. (2019). Necessity entrepreneurship and industry choice in new firm creation. Strategic Management Journal 40(13), 2165 to 2190. doi 10.1002/smj.3075. The page quotes one sentence of its abstract, published under CC BY.
- The code in this repository is under the MIT licence (see `LICENSE`).

Built with help from Claude; every number is fetched from Statistics Denmark and the ILO by the scripts in this repository.
