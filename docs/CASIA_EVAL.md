# CASIA v2 Evaluation Runbook

This is the execution-plan harness for **A1b** in [EXECUTION_PLAN.md](./EXECUTION_PLAN.md):
evaluate the classical L2 forensics path on a held-out split of **CASIA v2**, using real
tampered/authentic images plus ground-truth masks.

## What this slice does

- Adds a CASIA v2 dataset loader at `ml/layer2_forensics/dataset.py`
- Adds a CPU-only eval CLI at `ml/layer2_forensics/eval.py`
- Reports:
  - image-level discrimination (`auroc`, `accuracy`)
  - mask-level localization (`mean_iou`, `mean_f1`, `mean_precision`, `mean_recall`)
  - split composition and mask coverage

## What this slice does not do

- It does **not** claim a CASIA number by itself.
- It does **not** download the dataset automatically.
- It does **not** hide noisy/missing masks; the report tells you how many tampered images had
  no usable mask.

## Expected dataset layout

Use a CASIA v2 checkout organized like:

```text
CASIA2/
├── Au/
├── Tp/
└── Gt/
```

- `Au/` contains authentic images
- `Tp/` contains tampered images
- `Gt/` contains mask files named like `<tampered_stem>_gt.png`

The loader also accepts lowercase variants (`au`, `tp`, `gt`) and `Groundtruth/`.

## Recommended source

The widely shared CASIA v2 masks have known rotation and size issues on some files. Prefer
the corrected ground-truth packaging referenced in `docs/COMPETITORS.md` research notes.

## Exact runtime requirements

- Python environment with the repo's backend + ML dependencies
- `PYTHONPATH` including the repo root and `backend/`
- No GPU required

From a clean checkout, the command shape is:

```powershell
$env:PYTHONPATH='D:\PROJECTS\Startup\TruthPixel-l2-casia-eval;D:\PROJECTS\Startup\TruthPixel-l2-casia-eval\backend'
& 'D:\PROJECTS\Startup\TruthPixel\backend\.venv\Scripts\python.exe' -m ml.layer2_forensics.eval `
  --data-root 'D:\datasets\CASIA2' `
  --report-path 'artifacts\casia_v2_classical_eval.json'
```

Optional flags:

```text
--eval-split test
--val-fraction 0.1
--test-fraction 0.2
--localization-threshold 0.5
```

## Output contract

The report JSON includes:

- `split_summary`
- `evaluation.auroc`
- `evaluation.accuracy`
- `evaluation.localization.mean_iou`
- `evaluation.localization.mean_f1`
- `evaluation.localization.skipped_missing_masks`

This report is the input artifact for the future `docs/BENCHMARK.md` entry. Until the report
exists for a real local dataset, TruthPixel should not claim an A1b CASIA benchmark number.
