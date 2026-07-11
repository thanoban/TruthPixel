# Benchmark Report

> Publication artifact for the benchmark state that is actually reproducible from the current
> repo snapshot. This file includes only numbers that are present in tracked artifacts or in
> tracked docs that explicitly record produced run output. Where the repo does not yet contain a
> result, this file says so directly and leaves the exact next command path.

Part of the TruthPixel doc suite: [ML_PLAN.md](ML_PLAN.md) · [ROADMAP.md](ROADMAP.md) ·
[EXECUTION_PLAN.md](EXECUTION_PLAN.md) · [KAGGLE_TRAINING.md](KAGGLE_TRAINING.md)

## 1. Audit summary

| Area | Current status | Evidence in repo |
|---|---|---|
| L1 held-out-generator eval | **Produced** | `backend/models/l1_clip_head.metadata.json` + `docs/KAGGLE_TRAINING.md` |
| L1 robustness matrix | **Partially published** | Headline `screenshot_sim` metric is explicit; full per-variant values are **not** preserved in a tracked `eval_report.json` |
| L2 / CASIA eval | **Missing** | No `docs/CASIA_EVAL.md`; no committed CASIA result artifact or eval harness in this tree |
| Learned fusion benchmark | **Missing** | `ml/fusion/` tooling exists, but there is no committed training input, exported artifact, or published metrics |
| Calibration / ECE | **Missing** | Runtime/training code supports calibration export, but no committed held-out predictions or ECE artifact exist |
| Robustness matrix beyond L1 | **Missing** | No committed fusion-level or L2 robustness artifact exists |

## 2. Published benchmark numbers

### 2.1 L1 AI-generation detector

This is the only benchmark area with a verifiable produced result in the current repo state.

**Artifact provenance**
- Checkpoint metadata: `backend/models/l1_clip_head.metadata.json`
- Run instructions and recorded eval output: `docs/KAGGLE_TRAINING.md`
- Eval code: `ml/layer1_aigen/eval.py`

**Training/eval setup recorded in tracked files**
- Encoder: `ViT-L-14` pretrained on `openai`
- Probe head: MLP, hidden dim `512`, dropout `0.2`
- Held-out generators: `flux`, `midjourney`, `sdxl`
- Split sizes from tracked checkpoint metadata:
  - Train: `9589` total (`4790` real, `4799` generated)
  - Validation: `1235` total (`607` real, `628` generated)
  - Test: `1201` total (`603` real, `598` generated)
- Training run metadata from tracked checkpoint metadata:
  - Epochs: `5`
  - Batch size: `32`
  - Learning rate: `1e-4`
  - Validation fraction: `0.1`
  - Test fraction: `0.1`
  - Output dir recorded in metadata: `/kaggle/working/checkpoints/l1_aigen/run_20260710_0737`

**Verifiable published metrics**

| Metric | Value | Source |
|---|---:|---|
| Held-out `screenshot_sim` AUROC | `0.9688` | `docs/KAGGLE_TRAINING.md` checklist and eval instructions |
| Held-out `screenshot_sim` accuracy | `0.8959` | `docs/KAGGLE_TRAINING.md` checklist |
| Best validation accuracy | `0.8907` | `backend/models/l1_clip_head.metadata.json` |
| Final train accuracy | `0.8904` | `backend/models/l1_clip_head.metadata.json` |
| Final validation accuracy | `0.8891` | `backend/models/l1_clip_head.metadata.json` |

**What is not preserved exactly**
- The repo states that the L1 robustness matrix "holds up across all 4 variants" and that the
  AUROC range is `0.9688` to `0.9728`, but the tracked repo snapshot does **not** include the
  exact per-variant rows from `eval_report.json`.
- Because the tracked `eval_report.json` is absent, this report does **not** invent exact values
  for `pristine`, `jpeg_q75`, or `social_roundtrip`.

### 2.2 L2 edit forensics / CASIA

No CASIA benchmark number is publishable from the current tree.

**What is present**
- Planning references to CASIA in `docs/EXECUTION_PLAN.md` and `docs/ARCHITECTURE.md`

**What is missing**
- No `docs/CASIA_EVAL.md`
- No committed CASIA result JSON/CSV/Markdown artifact
- No committed CASIA eval script in this tree
- No published AUROC / IoU / localization result for L2

### 2.3 Learned fusion

No learned-fusion benchmark number is publishable from the current tree.

**What is present**
- Training/export code: `ml/fusion/train_meta.py`
- Feature layout: `ml/fusion/features.py`
- Runtime loader contract: `backend/app/fusion/learned.py`
- Test coverage proving artifact export shape: `ml/tests/test_fusion_train.py`,
  `backend/tests/test_fusion_engine.py`

**What is missing**
- No labeled claims JSONL committed for training
- No committed exported artifact (`manifest.json`, `model.json`, `calibration.csv`)
- No published precision@review-budget
- No published AUROC/Brier numbers from a real trained fusion artifact

### 2.4 Calibration / ECE / reliability

No ECE or reliability-diagram number is publishable from the current tree.

**What is present**
- `ml/fusion/train_meta.py` exports calibrated probabilities and Brier score metrics when a
  learned fusion model is trained
- Exported model metadata includes:
  - `auroc_raw`
  - `auroc_calibrated`
  - `brier_raw`
  - `brier_calibrated`

**What is missing**
- No committed trained fusion artifact
- No held-out prediction table for L1 or fusion
- No ECE helper or reliability-diagram artifact checked in

## 3. Metric definitions

These definitions match the current repo's benchmark intent.

| Metric | Definition in this project |
|---|---|
| AUROC | Area under the ROC curve; for `ml/layer1_aigen/eval.py`, computed over held-out real vs generated samples for each perturbation variant |
| Accuracy | Fraction of correct predictions at a fixed `0.5` threshold in `ml/layer1_aigen/eval.py` |
| Held-out generators | Generator families excluded from training and used only in test evaluation; current tracked L1 held-out set is `flux`, `midjourney`, `sdxl` |
| Robustness matrix | The same evaluation repeated across `pristine`, `jpeg_q75`, `screenshot_sim`, and `social_roundtrip` |
| Precision@review-budget | Planned fusion headline metric: precision among the top-k highest-risk claims a reviewer can actually inspect |
| Brier score | Mean squared error between predicted probabilities and true labels; emitted by `ml/fusion/train_meta.py` for learned fusion artifacts |
| ECE | Expected Calibration Error; planned metric in `docs/EXECUTION_PLAN.md`, but not yet produced by a committed artifact |

## 4. Exact command paths

### 4.1 Re-run the produced L1 benchmark

The benchmark command path for the shipped L1 checkpoint is the one documented in
`docs/KAGGLE_TRAINING.md` and implemented by `ml/layer1_aigen/eval.py`.

From the Kaggle notebook's `ml/` directory:

```bash
python -m layer1_aigen.eval \
  --data-root /kaggle/working/data/l1_aigen \
  --checkpoint /kaggle/working/checkpoints/l1_aigen/<RUN_ID>/l1_clip_head.pt \
  --report-path /kaggle/working/checkpoints/l1_aigen/<RUN_ID>/eval_report.json \
  --device cuda \
  --heldout-generators midjourney,sdxl,flux
```

Expected output artifact:
- `/kaggle/working/checkpoints/l1_aigen/<RUN_ID>/eval_report.json`

### 4.2 Produce the missing CASIA benchmark

This repo snapshot does **not** yet contain a CASIA eval harness. The next reproducible path is
therefore blocked on adding that harness first; until then there is no honest command in-tree to
run and cite.

Current blockers:
- `backend/app/forensics_classic.py` is not yet a published benchmark harness
- No CASIA dataset-prep doc or script is committed here
- No `docs/CASIA_EVAL.md` exists

### 4.3 Produce the missing learned-fusion benchmark

Once a labeled claims JSONL exists, the current tree already has the training/export command:

```bash
python -m ml.fusion.train_meta \
  --input <PATH_TO_LABELED_CLAIMS_JSONL> \
  --output-dir <OUTPUT_DIR> \
  --model-name learned-fusion-logreg-v1 \
  --calibration-fraction 0.3 \
  --random-state 7 \
  --shap-background-size 128
```

Expected output artifacts:
- `<OUTPUT_DIR>/manifest.json`
- `<OUTPUT_DIR>/model.json`
- `<OUTPUT_DIR>/feature_table.csv`
- `<OUTPUT_DIR>/calibration.csv`
- `<OUTPUT_DIR>/shap_background.csv`

What this command can publish today once run:
- `auroc_raw`
- `auroc_calibrated`
- `brier_raw`
- `brier_calibrated`
- training/calibration row counts

What it still does **not** publish by itself:
- Precision@review-budget
- ECE
- Reliability diagram
- Fusion robustness matrix

## 5. Blocked items

These benchmark deliverables are still blocked in the current repo snapshot:

| Deliverable | Blocker |
|---|---|
| L2/CASIA number | No committed eval harness, result artifact, or setup doc in this tree |
| Fusion headline metric | No labeled training set committed; no exported fusion artifact committed |
| ECE / reliability diagram | No held-out prediction artifact committed; no ECE helper committed |
| Full L1 per-variant robustness table | `eval_report.json` from the recorded Kaggle run is not committed |
| Fusion-level robustness matrix | No fusion benchmark run or artifact committed |

## 6. What this report does and does not claim

This report **does claim**:
- TruthPixel has one published benchmark result for L1 on held-out generators:
  `0.9688` AUROC and `0.8959` accuracy on `screenshot_sim`
- The shipped checkpoint metadata records the exact model family, split sizes, and training
  summary for that run

This report **does not claim**:
- Any CASIA number
- Any learned-fusion number
- Any ECE number
- Any exact per-variant L1 robustness values beyond the tracked `screenshot_sim` headline and
  the tracked AUROC range statement
