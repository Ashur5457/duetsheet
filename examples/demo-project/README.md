# Demo project

A complete Duetsheet project folder with synthetic data (not experimental results).

- `report.json`: the demo report
- `data/cycle1-runs.csv` to `cycle3-runs.csv`: raw data, one file per cycle
- `scripts/combine_cycles.py` and `derived_data/cycles1-3.csv`: the script that combines them, and its result, which is the report's dataset. The run is recorded as a step, so each chart shows its data chain (click the *Source* line under it)
- `data/cycle4-runs.csv`: a fourth cycle of runs, not imported yet (try **Import** in the Folder tab)
- `habits/`: an SVG figure and a matplotlib style (try **Learn my habits**)

Start it with `python duetsheet.py examples/demo-project` from the repository folder, or open [`duetsheet.html`](../../duetsheet.html) in Chrome or Edge, click **Open project folder**, and choose this folder. The page saves your changes into `report.json`, so work on a copy if you want to keep the original. See the [tutorial](../../docs/tutorial.md).
