# Learned Fusion Training

This is the **A5** bridge in the execution plan: take the A4 synthetic fraud-pair dataset,
convert it into labeled fusion-training rows using the current analyzer stack, then train and
export a backend-loadable learned-fusion artifact.

## Step 1 — Build labeled fusion rows

```powershell
$env:PYTHONPATH='D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5;D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5\backend'
& 'D:\PROJECTS\Startup\TruthPixel\backend\.venv\Scripts\python.exe' -m ml.fusion.build_training_set `
  --dataset-root 'D:\datasets\truthpixel-fraud-pairs' `
  --manifest 'D:\datasets\truthpixel-fraud-pairs\manifest.jsonl' `
  --output 'D:\datasets\truthpixel-fraud-pairs\fusion_train.jsonl'
```

This produces JSONL rows shaped for `ml.fusion.train_meta`:

- `label`
- `signals`
- `agent_findings`
- `source` metadata copied from the fraud-pair manifest

By default this stays local/CPU-friendly and does **not** require Vertex agents.

## Step 2 — Train and export the artifact

```powershell
$env:PYTHONPATH='D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5;D:\PROJECTS\Startup\TruthPixel-learned-fusion-a5\backend'
& 'D:\PROJECTS\Startup\TruthPixel\backend\.venv\Scripts\python.exe' -m ml.fusion.train_meta `
  --input 'D:\datasets\truthpixel-fraud-pairs\fusion_train.jsonl' `
  --output-dir 'D:\datasets\truthpixel-fraud-pairs\fusion_model'
```

The exported metrics now include:

- `auroc_*`
- `brier_*`
- `ece_*`
- `precision_at_review_budget_*`

## Step 3 — Verify backend runtime loading

Point the backend at the exported manifest:

```text
FUSION_MODEL_PATH=D:\datasets\truthpixel-fraud-pairs\fusion_model\manifest.json
```

The runtime will use the learned model automatically when the contract matches; otherwise it
logs a warning and falls back to the weighted fusion path.

## Honesty note

An artifact trained only on A4 synthetic labels is useful for calibration experiments and
pipeline verification, but it is **not** the final production fusion model. The roadmap's
end-state is A4 labels plus real reviewer decisions, then A6 benchmark publication.
