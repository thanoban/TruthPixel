# ML Plan — Models, Training, Evaluation

> What we train, what we don't, and how we prove it honestly.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [AGENTS.md](AGENTS.md) · [ROADMAP.md](ROADMAP.md) ·
> [COLAB_TRAINING.md](COLAB_TRAINING.md) (no local GPU — train T1 on Colab, data lives in Drive)

## 0. Scope discipline

We train exactly **three things**, in this order:

| # | Model | Phase | Compute |
|---|---|---|---|
| T1 | L1 CLIP-head (frozen ViT-L/14 features → MLP head) | 0 | Hours on one consumer GPU / free Colab |
| T2 | Fusion meta-classifier (GBM/LogReg over signal features) | 1 | Minutes on CPU |
| T3 | L3 recapture CNN (EfficientNet-B0-class) | 2 | Hours on one GPU |

Everything else is pretrained inference (TruFor, DINOv2) or third-party (Sightengine, c2patool).

**Day-one L1 without training anything:** before T1 is trained, L1 already runs as an
**ensemble of pretrained HF-Inference-API detectors** (`backend/app/hf_inference.py`) — zero
training, zero GPU hosting. T1 (our own screenshot-augmented head) is the *upgrade* that later
takes precedence or joins the ensemble as another member, not a prerequisite for a working,
reasonably accurate L1. See [ARCHITECTURE.md](ARCHITECTURE.md) §3a. So "train three things" is
about the moat, not about getting to a first working detector.

## 1. T1 — Layer-1 AI-generation detector

**Before T1 exists — the HF ensemble (shipped):** `HF_API_TOKEN` + `L1_HF_MODELS` makes L1 call
pretrained detectors via HF Inference API and average them (Apache-2.0 defaults: Ateeqq SigLIP
+ Nahrawy Swin). This is the day-one detector. T1 below is the accuracy upgrade — a head tuned
for *our* domain (product photos) and *our* threat model (screenshot survival), which generic
pretrained detectors are not trained for.

**Recipe (UniversalFakeDetect approach):**
1. Frozen CLIP ViT-L/14 image encoder → 768-d features.
2. Train a small head (linear probe first; 2-layer MLP if it clearly helps) on real-vs-generated.
3. Optionally train NPR (tiny CNN) as an independent second opinion; average at fusion.

**Data:** GenImage (primary), + ForenSynths for GAN-era coverage, + our own SDXL/Flux
"damaged product" generations for domain-specific hard positives. Real side: e-commerce-like
photos (product shots, phone photos), not just ImageNet.

**The screenshot-augmentation pipeline (applied to BOTH classes, ~50% of samples):**
```
random subset of, in random order:
  resize 0.5–1.5x (bilinear/bicubic mix)
  JPEG recompress q ∈ [65, 95]        (1–2 rounds — social-media roundtrip)
  random crop 85–100%
  slight gaussian blur (p=0.2)
  screenshot border/UI-strip crop simulation (p=0.1)
```
Purpose: the head must learn artifacts that survive screenshots/re-saves, not pristine-image
fingerprints. This single choice is the difference between demo accuracy and field accuracy.

**Class balance & domain:** 50/50 real/generated within each generator bucket; keep a
product-photo-heavy real distribution to match deployment.

**Calibration:** temperature-scale the head on a held-out validation split so its probability
is meaningful before it reaches fusion.

## 2. T2 — Fusion meta-classifier

- **Features:** per-layer `(score, confidence, available?)` + agent findings scores + the
  recapture×metadata-absent interaction term. Feature-dropout during training so any missing
  signal degrades gracefully.
- **Model:** gradient-boosted trees (LightGBM) or logistic regression — favor the simplest
  model that calibrates well.
- **Calibration:** Platt/isotonic on held-out claims; report reliability curves.
- **Explainability:** SHAP values per signal → the "why" section of the reviewer report.
- **Labels:** Phase 0 has none (use hand-tuned weighted average — already implemented in
  `backend/app/fusion/engine.py`). Phase 1 labels come from synthetic fraud pairs + reviewer
  decisions (the feedback loop).

## 3. T3 — Recapture classifier (Phase 2)

4-class: `direct-capture | screenshot | photo-of-screen | print-recapture`.
- Backbone: EfficientNet-B0 or MobileNetV3 (must be cheap — runs on every claim).
- Features that matter: moiré patterns, screen-pixel grid, glare/reflection, aliasing,
  status-bar/UI remnants, resampling traces. High-res patches, not just downscaled global view.
- Dataset: **built by us** — see COMPETITORS.md §8; scripted capture across devices.
- Until T3 ships, Sightengine recapture API fills L3.

## 4. Evaluation protocol — the honest number

**Held-out-generator evaluation is the only headline metric we quote:**
```
train on: SD1.x, SD2.x, GLIDE, VQDM, BigGAN (GenImage buckets)
test on:  Midjourney, SDXL, Flux, and any post-training-cutoff generator
```
Report AUROC + accuracy@fixed-FPR on the held-out bucket. Never quote same-generator numbers
as the headline.

**Robustness matrix** — every eval runs across perturbation columns:
| Condition | Why |
|---|---|
| pristine | ceiling |
| JPEG q75 | re-save |
| screenshot-sim (resize+recompress+crop) | the evasion case |
| social-roundtrip (double recompress) | WhatsApp/Instagram reality |

**Fusion eval:** end-to-end on a claims test set (synthetic fraud + legit claims):
precision@review-budget (top-k flagged), calibration error (ECE), and per-layer ablations
(drop each layer, measure fusion delta — proves fusion is the accuracy story).

**Regression gate:** any new model version must beat current on held-out-generator AUROC and
not regress the robustness matrix by >1pt anywhere. Versions logged in the model registry.

## 5. Repository layout for ML work

`ml/layer1_aigen/`, `ml/fusion/`, and `ml/tests/` exist today. `layer1_aigen/` already has the
working `dataset.py`, `augment.py`, `model.py`, `train.py`, `eval.py` scaffold (see
[COLAB_TRAINING.md](COLAB_TRAINING.md) for how to run it without a local GPU), and `fusion/`
already contains feature assembly plus training/export helpers. `ml/recapture/` and
`ml/datagen/` below are still target layout, not yet created.

```
ml/
  layer1_aigen/
    dataset.py      # GenImage loaders, generator-bucket splits
    augment.py      # screenshot-simulation pipeline (shared with eval)
    model.py        # frozen CLIP + head; NPR optional
    train.py        # linear-probe / MLP training loop
    eval.py         # held-out-generator protocol + robustness matrix
  fusion/
    features.py     # signal vector assembly (mirrors backend schemas)
    train_meta.py   # LightGBM/LogReg + calibration + SHAP export
  recapture/        # Phase 2
  datagen/
    gen_synthetic.py    # SDXL/Flux "damaged product" generation
    fraud_pairs.py      # inpainted-damage pairs from listing photos
```

## 6. Compute & hosting

- **Training:** no local GPU available — train on Colab's free T4 tier (see
  [COLAB_TRAINING.md](COLAB_TRAINING.md); data/checkpoints live in Google Drive, $0 cost).
  **Do not plan on GCP/Vertex credits for training compute** — the available $1,000 credit is
  scoped to GenAI App Builder (Vertex AI Search/Conversation/Agent Builder) and does **not**
  cover Colab Enterprise GPU or general Vertex training compute; confirmed by checking the
  credit's Billing → Credits scope. If training volume ever outgrows free Colab, evaluate a
  paid GPU option on its own merits rather than assuming this credit applies.
- **Inference:** local during dev → Modal/RunPod serverless scale-to-zero in Phase 1
  (claims are async & bursty; an always-on GPU box is wasted money).
- **Caching:** CLIP/DINOv2 embeddings computed once per image, reused by L1 and L5.
