# Fusion Robustness Evaluation

This is the **A5b** execution-plan slice: run the current L2 + fusion stack across the existing
robustness variants (`pristine`, `jpeg_q75`, `screenshot_sim`, `social_roundtrip`) on the A4
fraud-pair dataset.

## What it evaluates

- fused risk score under each robustness condition
- L2 score under each robustness condition
- `fused_auroc`
- `fused_accuracy`
- `fused_precision_at_review_budget`
- `fused_review_rate`
- `l2_auroc`
- `l2_accuracy`

## Command

```powershell
$env:PYTHONPATH='D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5;D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5\backend'
& 'D:\PROJECTS\Startup\TruthPixel\backend\.venv\Scripts\python.exe' -m ml.fusion.robustness_eval `
  --dataset-root 'D:\datasets\truthpixel-fraud-pairs' `
  --manifest 'D:\datasets\truthpixel-fraud-pairs\manifest.jsonl' `
  --report-path 'artifacts\fusion_robustness_report.json'
```

Optional:

```text
--fusion-model-path D:\datasets\truthpixel-fraud-pairs\fusion_model\manifest.json
--review-budget-fraction 0.1
--limit 200
```

## Scope honesty

- This report is for the A4 synthetic fraud-pair set, not a published external benchmark.
- For external splice benchmarking, use the A1b CASIA harness separately.
- If `--fusion-model-path` is omitted, the report evaluates the weighted fallback fusion path.
