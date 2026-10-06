# Homework 2: SPY

The notebook uses 1-minute SPY bars to clean and analyze the data, then design a simple correlation trading rule. It stops at long/short/flat signals; there is no backtest or P&L calculation.

Open `SPY_Simple_Correlation_Strategy.ipynb` and run the cells from the top. Saved outputs are included so the plots and results can also be read on GitHub.

The main rule correlates the previous minute's EMA distance with the following observed close-to-close return, using 60 complete pairs. RSI and an ATR-scaled move are comparisons. After each bar closes, a strong enough positive or negative correlation gives a proposed direction; otherwise the signal stays flat.

The sample covers **15 sessions, September 14–October 2, 2026**. The notebook uses the full sample for descriptive statistics and plots. It does not select settings based on trading returns.

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

Kalman smoothing is used for indicators. The observed prices stay available for the data summary. The signal checks cover information timing and the rule's direction; they do not evaluate trading performance.
