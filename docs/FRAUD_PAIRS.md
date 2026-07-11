# Synthetic Fraud Pairs

This is the **A4** execution-plan slice from [EXECUTION_PLAN.md](./EXECUTION_PLAN.md): a
locally generated, honestly labeled dataset of `listing -> claim` pairs built from real photos.

## Purpose

This dataset is for:

- calibrating the classical L2 score on self-authored splices
- per-layer ablations
- training/evaluating the future learned-fusion step (A5)

This dataset is **not** the accuracy claim. The external benchmark for L2 remains CASIA v2.

## What the generator creates

For each real source image:

- one `label=0` clean claim example with only mild recompress/resize/blur transforms
- one `label=1` synthetic fraud example with a mismatched-compression donor patch composited
  into the image plus a binary/soft mask

Outputs:

- `listing/`
- `claim/`
- `mask/`
- `manifest.jsonl`
- `summary.json`

## Manifest contract

Each JSONL row includes:

- `example_id`
- `split`
- `label`
- `pair_kind`
- `source_image`
- `donor_image`
- `listing_image`
- `claim_image`
- `mask_image`
- `operations`
- `synthetic_label_note`

The `synthetic_label_note` field is intentional: downstream users should not mistake these
rows for organic fraud cases.

## Command

```powershell
$env:PYTHONPATH='D:\PROJECTS\Startup\TruthPixel-fraud-pairs-datagen;D:\PROJECTS\Startup\TruthPixel-fraud-pairs-datagen\backend'
& 'D:\PROJECTS\Startup\TruthPixel\backend\.venv\Scripts\python.exe' -m ml.datagen.fraud_pairs `
  --input-root 'D:\datasets\listing-photos' `
  --output-root 'D:\datasets\truthpixel-fraud-pairs'
```

Useful flags:

```text
--seed 7
--max-images 500
--max-edge 1024
--val-fraction 0.1
--test-fraction 0.2
```

## Notes

- Uses only PIL/numpy; no GPU required
- Keeps labels honest by marking fraud rows as synthetic compositing
- Produces masks so future L2 calibration and robustness checks can be localized, not just
  image-level
