# Benchmark

This document is the reference for measured model results that already exist in the repo.

## 1. Current published result

The only trained-model benchmark currently documented with committed evidence is the Layer 1
CLIP-head run stored alongside the backend checkpoint metadata.

**Model:**

- L1 local CLIP-head checkpoint
- encoder: `ViT-L-14` (`openai` pretrained)
- head: 2-layer MLP, hidden size `512`, dropout `0.2`
- held-out generators: `sdxl`, `midjourney`, `flux`

**Training run metadata:**

- run path: `/kaggle/working/checkpoints/l1_aigen/run_20260710_0737`
- epochs: `5`
- batch size: `32`
- learning rate: `1e-4`

## 2. Headline metric

Held-out-generator benchmark on the `screenshot_sim` condition:

- **AUROC: `0.9688`**
- **Accuracy: `0.8959`**

This is the main number referenced in the roadmap because it is the most honest field-style
metric currently recorded for the trained L1 path.

## 3. Robustness matrix summary

Across the four evaluation variants already referenced in project docs:

- pristine
- `jpeg_q75`
- `screenshot_sim`
- `social_roundtrip`

The recorded AUROC range is:

- **`0.9688` to `0.9728`**

That means the held-out-generator score stayed strong across the recompression and screenshot-like
conditions used by the current evaluation workflow.

## 4. Training and validation snapshot

From the committed checkpoint metadata file:

- best validation accuracy: `0.8907`
- final training accuracy: `0.8904`
- final validation accuracy: `0.8891`

This is the repo-backed source of truth for the run summary and should be preferred over older
notes if any document disagrees.

## 5. Data split summary

From the same committed metadata:

- train: `9589` total (`4790` real, `4799` generated)
- val: `1235` total (`607` real, `628` generated)
- test: `1201` total (`603` real, `598` generated)

## 6. What this benchmark does and does not prove

What it proves:

- the local L1 checkpoint path is not only scaffolded; it has a real trained artifact
- the current L1 model performs strongly on the held-out-generator screenshot-style benchmark
- the run does not show obvious train/val overfitting in the recorded summary

What it does not prove:

- whole-system production accuracy
- learned-fusion accuracy, because no fusion model artifact is trained yet
- external splice-forensics performance for L2 on a public benchmark
- reviewer-workflow precision at a fixed review budget

## 7. Current benchmark gaps

These are still external or not yet measured in committed docs:

- L2 external benchmark number for TruFor or the classical fallback path
- learned-fusion benchmark from labeled claims
- full end-to-end business metric such as precision at review budget
- future L3 custom recapture model benchmark

## 8. Source files for these numbers

- `backend/models/l1_clip_head.metadata.json`
- `docs/ROADMAP.md`
- `docs/KAGGLE_TRAINING.md`

If these files ever disagree, update the docs to match the committed artifact metadata first.
