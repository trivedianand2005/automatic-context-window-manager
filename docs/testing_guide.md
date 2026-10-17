# Hands-on testing guide

The live site (<https://acwm-web.onrender.com>) can index two bundled example repositories.
Other paths are rejected on the hosted demo for security.

| Repository | What it is | Size | Labelled benchmark |
|---|---|---|---|
| **ShopAPI** (`examples/sample_fastapi_repo`) | FastAPI web service: auth, orders, database retry | 49 files, ~9.8k tokens | Yes (5 tasks; the heuristics were tuned on it) |
| **LibTrack** (`examples/sample_library_repo`) | Library management: catalog, loans, late fees, e-mails | 21 files, ~4.5k tokens | No. It is a held-out repository and ACWM was **not** tuned on it |

## Testing LibTrack yourself

1. Open **Repository** and click the **LibTrack** card. It indexes immediately.
2. Open **Build context**. The example chips now show LibTrack tasks.
3. Pick a task, set the budget (try 3000, then 6000), and click **Build context**.
4. On **Results**, check whether the files below were selected and read *why* each file
   was chosen.
5. On **Compare**, choose **Custom (no labels)** and run the comparison to see what each
   method picks.

### Tasks and the files a developer would need

These are reasonable answers written by the repository's author. Judge the results
against them.

| Task | Files you would expect |
|---|---|
| Fix the off-by-one bug in the late fee calculation and add regression tests. | `libtrack/fines.py` (the bug is in `overdue_days`), `libtrack/utils/dates.py`, `libtrack/loans.py` (calls `calculate_fine`), `libtrack/config.py` (fee settings), `tests/test_fines.py`, `tests/test_loans.py` |
| Allow members to renew a loan at most twice. | `libtrack/loans.py` (`renew`), `libtrack/models.py` (`Loan.renewals`), `libtrack/config.py`, `tests/test_loans.py` |
| Add search by ISBN to the catalog. | `libtrack/catalog.py` (`search`), `libtrack/models.py` (`Book.isbn`), `libtrack/utils/text.py`, `tests/test_catalog.py` |
| Send overdue reminder emails to members. | `libtrack/notifications.py`, `libtrack/loans.py` (`overdue`), `libtrack/models.py`, `libtrack/config.py` |

### What we measured (honest results)

We ran the comparison API at a total budget of 3000 (about 920 usable tokens) on
2026-10-18. Coverage is the share of the expected files that were selected:

| Task | Baseline | + Dependency | Full ACWM |
|---|---|---|---|
| Late fee off-by-one | 0.33 | 0.33 | 0.33 |
| Renewal limit | 0.25 | 0.50 | **0.75** |
| ISBN search | 0.50 | **1.00** | 0.75 |
| Overdue e-mails | 0.50 | 0.50 | 0.50 |

On this unseen repository ACWM is **not** consistently better. That is an expected and
useful result, and it shows the limits of the approach.

### A limitation you can see for yourself: vocabulary mismatch

The task says **"late fee"**, but the code says **"fine"** (`fines.py`,
`calculate_fine`). ACWM's retrieval is lexical (BM25 plus a small synonym list), so it
does not know the two words mean the same thing. It even selects
`notifications.py`, because that file literally contains "late fee".

Try these workarounds and compare the results:

* **Rephrase the task in the code's vocabulary** (measured; this works): *"Fix the
  off-by-one bug in the fine calculation (overdue_days) and add regression tests."* ACWM's
  coverage rises from 0.50 to **1.00** at a 6000 budget (all six expected files), and from
  0.33 to 0.50 at 3000.
* **Name the function.** Identifiers such as `overdue_days` or `calculate_fine` get exact
  symbol matches.
* **Required files** (**Advanced options → Required files**) are always included and are
  placed first. With a small budget, a required file can use most of the space: at 3000,
  requiring `libtrack/loans.py` left room for nothing else. Use them with a larger budget.
* **Semantic search.** Install the optional semantic signal locally
  (`sentence-transformers`), which is meant for exactly this case. It is not available on
  the free hosting tier.

## Testing your own repository

Your own repositories cannot be indexed on the hosted demo. Run ACWM locally instead:

```bash
git clone https://github.com/trivedianand2005/automatic-context-window-manager.git
cd automatic-context-window-manager
python -m venv .venv && .venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
set ACWM_ALLOWED_ROOTS=C:\path\to\your\projects      # macOS/Linux: export ACWM_ALLOWED_ROOTS=/path/to/projects
uvicorn app.api.main:app --port 8000
# second terminal
cd frontend && npm ci && npm run dev                   # open http://localhost:5173
```

Then type your repository's path on the **Repository** page. Python files get full
symbol and dependency analysis. Markdown, JSON, YAML and TOML files are indexed as text.
