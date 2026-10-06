# Homework 2: SPY

The notebook uses 1-minute SPY bars to look at cleaning, smoothing, and a simple correlation trading rule.

Open `SPY_Simple_Correlation_Strategy.ipynb` and run the cells from the top. Saved outputs are included so the plots and results can also be read on GitHub.

The main rule correlates EMA distance with a later opening-price return. RSI and an ATR-scaled move are comparisons. Signals trade at the next open and positions close before the end of each session.

The sample actually covers **15 sessions, September 14–October 2, 2026**. The first 10 sessions are for inspection; the final 5 are the later test. At the assumed 0.5 bp cost per side, the main rule earns about 0.594% gross and loses 0.834% net in that later test. The notebook keeps the losing result and checks higher costs too.

## Run it locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/run_notebook.py
python -m unittest discover -s tests -v
```

You can also select that environment as the kernel in your notebook editor. The run script uses the Python environment it was launched with and saves outputs only after the full notebook finishes successfully.

## Data

`data/spy_1min.csv` contains 5,850 cleaned minute bars. `data/cleaning_audit.json` records the source hashes and every removal count. Both raw downloads have the same SHA-256 hash, so only one is used.

To rebuild, place either `qykjkjsbk5ycr4qh.csv` or `wyibfmmayut9nuxe.csv` beside the notebook and set `REBUILD = True`. The raw files are kept out of this branch because each is about 885 MB. Cached bars let a fresh clone run without them. With `REBUILD = False`, the loader verifies the saved bar file and cleaning version; set it to `True` when the raw source changes.

The loader checks the full 390-minute sessions in this sample. It raises an error for a missing minute or an early close rather than filling in made-up prices. New samples with early closes need an appropriate session calendar.

Kalman smoothing is used for indicators. The backtest uses observed opening trade prices, not smoothed prices. There are no quotes in this extract, so actual spreads and fill quality cannot be measured here.
