# Training on Google Colab + Google Drive (no local GPU)

> Your laptop has no GPU and datasets shouldn't be downloaded locally — everything below runs
> **inside Colab** and reads/writes **Google Drive** only. Nothing touches your laptop disk.
> Hit Colab's GPU quota? See [KAGGLE_TRAINING.md](KAGGLE_TRAINING.md) for the same pipeline on
> Kaggle's free tier instead.
> Part of the TruthPixel doc suite: [ML_PLAN.md](ML_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [KAGGLE_TRAINING.md](KAGGLE_TRAINING.md) · [ROADMAP.md](ROADMAP.md)

## Contents

0. [What this covers](#0-what-this-covers)
1. [The mental model](#1-the-mental-model)
2. [One-time setup](#2-one-time-setup)
3. [Getting data into Drive](#3-getting-data-into-drive--without-downloading-to-your-laptop)
4. [Sanity-check the dataset](#4-sanity-check-the-dataset-before-training)
5. [Train](#5-train--reading writing-drive-directly)
6. [Evaluate](#6-evaluate--the-honest-held-out-generator-number)
7. [What happens with the checkpoint](#7-what-happens-with-the-trained-checkpoint-and-why-your-laptop-still-doesnt-need-a-gpu)
8. [Run versioning — don't silently overwrite past runs](#8-run-versioning--dont-silently-overwrite-past-runs)
9. [Resuming in a brand-new Colab session](#9-resuming-in-a-brand-new-colab-session)
10. [Troubleshooting](#10-troubleshooting)
11. [Time & cost estimates](#11-time--cost-estimates)
12. [Checklist](#12-checklist)

## 0. What this covers

Only **T1 — the L1 CLIP-head** (see [ML_PLAN.md](ML_PLAN.md) §1) is in scope here. It's the
one model in the whole system that (a) needs a GPU to train at reasonable speed and (b) is
cheap enough — a frozen CLIP encoder + a small trainable head — that Colab's free T4 tier is
genuinely enough. T2 (fusion meta-classifier) trains on CPU in minutes; T3 (recapture CNN) is
Phase 2 and gets its own doc when we get there.

Code already exists for this in the repo (`ml/layer1_aigen/`) — this doc is about **how to run
it on Colab against data that lives entirely in Drive**, not about writing new training code.

**Notebook name:** `TruthPixel_L1_Training.ipynb`. Create it at colab.research.google.com
("New notebook"), rename it via the title field at the top-left, then immediately
**File → Save a copy in Drive** and move it into `TruthPixel/notebooks/` (see the tree below)
so it survives across sessions like everything else here — a notebook left in Colab's default
"Untitled0.ipynb" location under "My Drive/Colab Notebooks/" is easy to lose track of once you
have more than one project going.

### Notebook structure at a glance

Every code block in this doc is one Colab cell, in this order, inside
`TruthPixel_L1_Training.ipynb`. Use a Colab **text cell** for each `##`-level heading below as
a section divider (Insert → Text cell) so the notebook is self-navigating — you shouldn't need
this doc open once the notebook is built once.

| Cell | Title | Section | What it does |
|---|---|---|---|
| 1 | Mount Drive & create folders | §2.2 | Mounts Google Drive, creates the `TruthPixel/` folder tree |
| 2 | Clone repo & install training deps | §2.3 | Fresh checkout of the code, installs `ml/requirements.txt` |
| 3 | Download CIFAKE (bootstrap) | §3.1 | Pulls the small sanity-check dataset via Kaggle API |
| 4 | Reshape CIFAKE into expected layout | §3.1 | Copies CIFAKE's `REAL/`/`FAKE/` into `real/`/`generated/` |
| 5 | Pull DiffusionDB subset | §3.2 | Streams a bounded AI-generated slice from Hugging Face straight to Drive |
| 6 | Real (non-AI) product-photo side | §3.3 | Fills `real/` with domain-matched or fallback photos |
| 7 | Generate held-out SDXL bucket | §3.4 | Self-generates a small genuinely-unseen-generator test bucket |
| 8 | Dataset sanity check | §4 | Confirms `discover_samples` finds a sane, balanced dataset before spending GPU time |
| 9 | Train | §5 | Runs `layer1_aigen.train`, writes the checkpoint to a timestamped Drive folder |
| 10 | Evaluate | §6 | Runs `layer1_aigen.eval`, produces the held-out robustness-matrix report |
| 11 | Log the run | §8 | Appends the run to `runs.log` so past experiments stay comparable |

Runtime action (not a cell): §2.4 sets the GPU type via the Runtime menu, not code.
Browser action (not a cell): §2.1 generates and uploads `kaggle.json`, done once outside Colab.

---

## 1. The mental model

```
Google Drive (persistent)
TruthPixel/
├── notebooks/
│   └── TruthPixel_L1_Training.ipynb   ← the Colab notebook itself, saved here
├── kaggle.json                        ← API credential, uploaded once (§2.1)
├── data/l1_aigen/
│   ├── real/...
│   └── generated/<generator>/...
└── checkpoints/l1_aigen/
    └── run_<YYYYMMDD_HHMM>/           ← one subfolder per training run, see §8
        ├── l1_clip_head.pt
        ├── l1_clip_head.metadata.json
        ├── history.json
        └── eval_report.json

Colab runtime (ephemeral, resets every session)
/content/TruthPixel/          ← git clone, recreated every session, ~seconds
  └── ml/                     ← the training code (dataset.py, augment.py, model.py, train.py, eval.py)
```

Rule of thumb: **code and pip packages are ephemeral** (recreated every session, that's fine,
it's fast) — **data and checkpoints live only on Drive** (`--data-root` and `--output-dir` always
point at `/content/drive/MyDrive/TruthPixel/...`). If Colab disconnects, you lose nothing
except the current in-progress epoch loop — the dataset and any *completed* checkpoint are
still on Drive.

---

## 2. One-time setup

### 2.1 Kaggle API credential (for dataset downloads)

1. On kaggle.com → Account → "Create New API Token" → downloads `kaggle.json`.
2. Upload that single small file to Google Drive at `TruthPixel/kaggle.json` (via drive.google.com
   in a browser — it's a few hundred bytes, not a dataset, so this doesn't violate "no local
   downloads" in spirit; if you'd rather avoid even that, generate the token from a phone/other
   device, or skip Kaggle entirely and use the Hugging Face path in §3.2 instead).

### 2.2 Drive folder structure

**Cell 1 — Mount Drive & create folders.** First cell of the notebook, run every session. The
`drive.mount()` call pops a Google auth flow the first time (click through, grant access) —
after that it's silent. The `os.makedirs(..., exist_ok=True)` loop is idempotent, so re-running
this cell in a later session is harmless — it won't wipe anything already there.

```python
from google.colab import drive
drive.mount('/content/drive')

import os
BASE = "/content/drive/MyDrive/TruthPixel"
for sub in ["notebooks", "data/l1_aigen/real/camera", "checkpoints/l1_aigen"]:
    os.makedirs(f"{BASE}/{sub}", exist_ok=True)
```

*Expect:* a "Mounted at /content/drive" message, and no errors from the loop. If you `!ls
/content/drive/MyDrive/TruthPixel` afterward you should see `notebooks/`, `data/`, `checkpoints/`.

### 2.3 Clone the repo + install deps (every session — fast)

**Cell 2 — Clone repo & install training deps.** Pulls a fresh copy of the codebase into the
Colab VM's local disk (`/content/TruthPixel`, *not* Drive — this is the ephemeral half of the
mental model in §1) and installs the Python packages `ml/layer1_aigen/` needs. Colab's base
image already ships `torch`/`torchvision` with CUDA wired up, so this is really just installing
`open_clip_torch`, `numpy`, and `pillow` on top — usually well under a minute.

```python
!git clone https://github.com/thanoban/TruthPixel.git /content/TruthPixel
%cd /content/TruthPixel/ml
!pip install -q -r requirements.txt   # torch/torchvision already present on Colab; installs open_clip_torch
```

*Expect:* the clone prints a "Cloning into..." + object-count summary; pip install ends with no
red `ERROR:` lines. If a later cell fails with `ModuleNotFoundError`, re-run this cell first —
it's the most common fix after a session was interrupted mid-install.

### 2.4 Runtime type

**Not a cell — a menu action**, done once per session before Cell 2 (or right after; either
order is fine, but training will error out at `--device cuda` if you forget it). Runtime →
Change runtime type → **T4 GPU** (free tier). The L1 head is tiny (frozen CLIP + 2-layer MLP),
so T4 is plenty — no need for A100/Colab Pro for this model.

---

## 3. Getting data into Drive — without downloading to your laptop

The trap to avoid: `GenImage` in full is ~1M+ images (hundreds of GB) — too big for free Drive
(15 GB) and too slow for a free Colab session. **Don't pull the full dataset.** Pull curated
subsets, directly from Colab into Drive, sized to fit both constraints.

Target layout (must match `ml/layer1_aigen/dataset.py::discover_samples`):

```
data/l1_aigen/
├── real/
│   └── <any-subfolder-name>/*.jpg        # label=0; subfolder name is cosmetic
└── generated/
    ├── sdxl/*.jpg                        # label=1, generator="sdxl"
    ├── midjourney/*.jpg                  # label=1, generator="midjourney"
    ├── sd1x/*.jpg
    └── flux/*.jpg
```

The **subfolder name under `generated/` becomes the generator bucket** used for held-out-generator
evaluation (`--heldout-generators midjourney,sdxl,flux` in train.py defaults) — name folders to
match exactly what you pass on the CLI.

### 3.1 Bootstrap / sanity-check set — CIFAKE (fast, small, do this first)

Confirms the whole pipeline (Drive paths, dataset discovery, training loop, checkpoint save)
works before spending Colab GPU-hours on anything bigger.

**Cell 3 — Download CIFAKE (bootstrap).** Points the `kaggle` CLI at the credential you
uploaded to Drive in §2.1 (`KAGGLE_CONFIG_DIR` tells it where to find `kaggle.json`, rather than
the usual `~/.kaggle/`), then downloads and unzips CIFAKE to the Colab VM's local disk — not
Drive yet, that happens in the next cell, since Kaggle's raw zip layout doesn't match what
`discover_samples()` expects.

```python
import os
os.environ["KAGGLE_CONFIG_DIR"] = "/content/drive/MyDrive/TruthPixel"  # finds kaggle.json there
!pip install -q kaggle
!kaggle datasets download -d birdy654/cifake-real-and-ai-generated-synthetic-images \
    -p /content/cifake --unzip
```

*Expect:* a download progress bar, then "Downloading ... to /content/cifake" completing without
a 401/403 (see §10 troubleshooting if you get one). The dataset is small (~130 MB), typically
under a minute on Colab's network.

**Cell 4 — Reshape CIFAKE into expected layout.** CIFAKE ships as `REAL/` and `FAKE/` folders;
our `dataset.py::discover_samples()` expects `real/<any-name>/` and `generated/<generator-name>/`
(§3, target layout above). This cell does that one-time relabel, copying straight to Drive so
it persists. CIFAKE's full `train` split is 100k images per class — more than a bootstrap
sanity-check needs and slower to sync to Drive than necessary, so this caps each side at 2,000
files (`glob` + slice) instead of copying everything (`shutil.copytree`).

```python
import os, shutil, glob

DRIVE = "/content/drive/MyDrive/TruthPixel/data/l1_aigen"
src = "/content/cifake/train"

os.makedirs(f"{DRIVE}/real/cifake_real", exist_ok=True)
os.makedirs(f"{DRIVE}/generated/cifake", exist_ok=True)

real_files = glob.glob(f"{src}/REAL/*")[:2000]
fake_files = glob.glob(f"{src}/FAKE/*")[:2000]

for f in real_files:
    shutil.copy2(f, f"{DRIVE}/real/cifake_real/")

for f in fake_files:
    shutil.copy2(f, f"{DRIVE}/generated/cifake/")

print("Copied real:", len(real_files))
print("Copied fake:", len(fake_files))
```

*Expect:* `Copied real: 2000` / `Copied fake: 2000` printed at the end. Note: CIFAKE is 32×32 —
too low-res for a production-quality head, but perfect for a first end-to-end run in under
10 minutes. Raise the `[:2000]` slice later if you want CIFAKE to contribute more volume beyond
the bootstrap pass.

### 3.2 Real training set — Hugging Face `datasets`, streamed, capped size

`DiffusionDB` and several `GenImage`-style mirrors are on Hugging Face and support pulling a
**bounded random subset** without touching your laptop — the download happens inside the Colab
VM and you write only the subset you keep to Drive.

**Cell 5 — Pull DiffusionDB subset.** Streams a pre-sampled slice of DiffusionDB (Hugging Face
handles the download; nothing lands on your laptop) and re-saves each image as a JPEG directly
into the Drive `generated/diffusiondb/` bucket. This is your main AI-generated training volume
(CIFAKE in Cells 3–4 was just the bootstrap). **Confirmed working** with the `streaming=True` +
`"default"` config fix below (2026-07-09 run).

```python
!pip install -q datasets
from datasets import load_dataset
import os

DRIVE = "/content/drive/MyDrive/TruthPixel/data/l1_aigen"
os.makedirs(f"{DRIVE}/generated/diffusiondb", exist_ok=True)

# DiffusionDB ships a custom loading script (diffusiondb.py). Recent `datasets` versions
# (>=3.0, what Colab installs by default) refuse to execute ANY community loading script —
# you'll hit "RuntimeError: Dataset scripts are no longer supported" without this pin.
# `refs/convert/parquet` is HF's auto-converted, script-free mirror — but it only preserved
# a single "default" config (not the per-size "2m_random_5k"-style configs), and "default"
# is the full ~2M-row dataset. Stream it and take a random slice instead of loading it whole.
ds = load_dataset(
    "poloclub/diffusiondb", "default", split="train",
    revision="refs/convert/parquet", streaming=True,
)
ds = ds.shuffle(seed=42, buffer_size=1000)
for i, row in enumerate(ds.take(5000)):
    row["image"].convert("RGB").save(f"{DRIVE}/generated/diffusiondb/{i:05d}.jpg", quality=92)
```

*Expect:* no upfront download progress bar (streaming reads parquet row-groups lazily as you
iterate), then a save loop with no printed output — expect this to take longer per-image than a
plain local copy since each one is fetched over the network on demand; that's normal for
`streaming=True`. Adjust volume via `.take(N)` — `1000` for a quicker pass, `10000` for more —
rather than a config-string change, since `refs/convert/parquet` only exposes `"default"`.

**If `refs/convert/parquet` doesn't work at all for a dataset you try later** (config truly
unavailable, not just renamed), fall back to pinning an older `datasets` version that still
runs scripts: `!pip install -q "datasets==2.19.0" "fsspec==2024.5.0"`, then call
`load_dataset("<repo>", "<config>", split="train", trust_remote_code=True)` (no `revision=`,
no `streaming=`/`.take()` needed since old-style configs are already pre-sized) — restart the
runtime first if you already imported the newer `datasets` in this session.

### 3.3 Real (non-AI) side — product-style photos

Domain match matters more than volume here (see ML_PLAN.md §1: "product-photo-heavy real
distribution to match deployment").

**Cell 6 — Real (non-AI) product-photo side.** Fills the `real/` bucket. Domain-matched product
photos are preferred (see ML_PLAN.md §1) but not always readily available as a clean Kaggle/HF
dataset — this cell uses a generic COCO fallback so the pipeline has *something* real to train
against; swap the source below for a Kaggle product-photo dataset (downloaded the same way as
Cell 3) whenever you find one that fits.

```python
!pip install -q datasets
from datasets import load_dataset
import os

DRIVE = "/content/drive/MyDrive/TruthPixel/data/l1_aigen"
os.makedirs(f"{DRIVE}/real/coco_fallback", exist_ok=True)

# Generic real-photo fallback — swap for a product-photo dataset when you have one.
ds = load_dataset("detection-datasets/coco", split="val", streaming=True)
for i, row in enumerate(ds.take(3000)):
    row["image"].convert("RGB").save(f"{DRIVE}/real/coco_fallback/{i:05d}.jpg", quality=92)
```

*Expect:* similar to Cell 5 — a streaming download, then a silent save loop; `.take(3000)` caps
it so this doesn't try to pull all of COCO. Other options, no cell needed:
- Kaggle product-photo datasets (search `kaggle datasets list -s "product images"`) — download
  the same way as Cell 3, write into `real/<name>/`.
- Your own phone photos of products, uploaded straight into Drive's `real/` folder from your
  phone's Google Photos → Drive integration — no laptop involved either.

### 3.4 Held-out generator bucket (SDXL / Flux / Midjourney)

For the headline held-out-generator metric (ML_PLAN.md §4) you need at least one generator
your training mix has genuinely never seen. Cheapest path on Colab:

**Cell 7 — Generate held-out SDXL bucket.** Runs Stable Diffusion XL directly on the Colab GPU
to self-generate a small, genuinely-unseen-generator bucket — this doubles as the "our own
SDXL/Flux hard positives" step from ML_PLAN.md §1. This is a separate, smaller run: generate a
few hundred images at most (each takes seconds on a T4; don't try to build training *volume*
this way, just enough for a clean held-out test set).

**Use a real prompt list, not 1-2 placeholder entries.** A too-short `prompts` list is an easy
trap — the held-out metric in §6 is meaningless off 2 images. Aim for 20-50+ distinct prompts
covering your target product categories; re-run this cell (safe to re-run — it appends, using
`existing` as an offset, rather than overwriting) if you need to top it up later.

```python
# Small self-generated held-out bucket using SDXL directly on the Colab GPU —
# this doubles as the "our own SDXL/Flux hard positives" step from ML_PLAN.md §1.
!pip install -q diffusers accelerate
from diffusers import StableDiffusionXLPipeline
import torch, os

if "pipe" not in dir():
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16
    ).to("cuda")

DRIVE = "/content/drive/MyDrive/TruthPixel/data/l1_aigen/generated/sdxl"
os.makedirs(DRIVE, exist_ok=True)
prompts = [
    "a cracked ceramic mug on a wooden table, product photo",
    "a torn leather shoe, damaged product return photo",
    "a scratched smartphone screen, product photo",
    "a dented aluminum water bottle, product photo",
    "a stained white t-shirt, damaged product return photo",
    "a broken plastic chair leg, product photo",
    "a chipped porcelain plate, product photo",
    "a ripped backpack strap, product photo",
    "a shattered glass vase, product photo",
    "a rusted metal toolbox, product photo",
    "a frayed electrical cable, product photo",
    "a cracked laptop screen, product photo",
    "a torn couch cushion, product photo",
    "a warped wooden cutting board, product photo",
    "a discolored running shoe sole, product photo",
    "a bent bicycle wheel, product photo",
    "a leaking water bottle cap, product photo",
    "a peeling non-stick pan coating, product photo",
    "a snapped umbrella rib, product photo",
    "a moldy bathroom mat, product photo",
    # add more damage-plausible prompts matching your target e-commerce categories
]

existing = len(os.listdir(DRIVE))  # so re-runs append instead of overwriting
for i, p in enumerate(prompts):
    img = pipe(p).images[0]
    img.save(f"{DRIVE}/{existing + i:04d}.jpg", quality=92)
print("Total sdxl images now:", len(os.listdir(DRIVE)))

# Free SDXL's GPU memory once you're done generating — its UNet + VAE + text encoders can
# hold 10+ GB resident on a T4, which starves Cell 9 (train) if you don't release it first.
del pipe
import gc
gc.collect()
torch.cuda.empty_cache()
```

*Expect:* a model-download progress bar the first time (SDXL weights, several GB, cached for
the rest of the session), then one progress step per prompt as each image generates
(a few seconds each on T4). The `del pipe` / `empty_cache()` cleanup at the end has no visible
output but is required if you plan to run Cell 9 in the same session — see §5.2.

---

## 4. Sanity-check the dataset before training

Cheap correctness check — do this every time you add data, before burning GPU minutes.

**Cell 8 — Dataset sanity check.** Runs the exact same `discover_samples()` /
`assign_splits()` functions that `train.py` uses internally, but standalone, so you can inspect
the split before committing GPU time to a bad dataset. `summarize_assignments()` prints
per-split real/generated counts — eyeball it for gross imbalance before moving on.

```python
%cd /content/TruthPixel/ml
from layer1_aigen.dataset import discover_samples, assign_splits, summarize_assignments

samples = discover_samples("/content/drive/MyDrive/TruthPixel/data/l1_aigen")
print(f"total samples: {len(samples)}")
assignments = assign_splits(samples, heldout_generators={"sdxl", "midjourney", "flux"})
print(summarize_assignments(assignments))
```

*Expect:* `total samples` in the thousands (roughly the sum of everything you loaded in Cells
3–7), and a `{"train": {...}, "val": {...}, "test": {...}}` dict with non-zero counts on both
`real` and `generated` in every split. If `total samples` is 0, the folder layout doesn't match
§3's structure — fix that before proceeding, training will otherwise fail with a clear
`RuntimeError` anyway.

---

## 5. Train — reading/writing Drive directly

**Cell 9 — Train.** The actual training loop: encodes every image through a frozen CLIP
ViT-L/14 (`open_clip`), backprops only through the small trainable head on top, and repeats for
`--epochs` passes over the data. Screenshot augmentation runs automatically on every training
batch, no separate step needed (details right after the code block below). Prints one JSON
line of `{epoch, train, val}` metrics per epoch to the cell output as it goes — watch
`val.accuracy` climb; if it stays flat near 0.5 across epochs, see §10 troubleshooting
("stuck at 50%").

**If you ran Cell 7 (SDXL) earlier in this same session, free its GPU memory first** — see
§5.2. Running straight from Cell 7 into Cell 9 without that cleanup is the single most common
way to hit `CUDA out of memory` here, and it happens on the very first batch (before any epoch
metrics print), which is the tell that it's leftover SDXL memory, not a genuinely too-large
`--batch-size`.

**Reading training images straight off the Drive mount is slow — copy to local disk first.**
The Drive FUSE mount does a network round-trip per file open, so a training pass over a few
thousand individual small JPEGs directly from `/content/drive/...` can take tens of minutes on
I/O alone, with GPU usage staying flat/idle the whole time (the tell that this, not compute, is
the bottleneck). Fix: copy the dataset to local Colab disk (`/content/`, fast) before training,
and point only `--output-dir` at Drive so the checkpoint still persists.

**Cap the copy per subfolder — don't blindly mirror everything.** This is the default,
**confirmed-working** approach — use it over plain `cp -r` even on a first run. It's easy for
the Drive-side dataset to balloon well past what you intended (e.g. an earlier uncapped run of
Cell 4 before switching to the 2,000-file cap leaves its output sitting there — nothing in §3
ever deletes old files when you re-run a cell with a smaller cap). A plain `cp -r` then copies
*all* of it, which can turn a "few thousand images, a couple minutes" copy into "tens of
thousands of files, tens of minutes" without you having changed anything else — this happened
in practice (Drive-side dataset had grown to 87k files against an intended ~15k).

```python
import os, shutil, glob

DRIVE_ROOT = "/content/drive/MyDrive/TruthPixel/data/l1_aigen"
LOCAL_ROOT = "/content/data/l1_aigen"
CAP_PER_FOLDER = 3000  # raise later once a first run works end-to-end

for label in ("real", "generated"):
    label_root = f"{DRIVE_ROOT}/{label}"
    if not os.path.isdir(label_root):
        continue
    for sub in os.listdir(label_root):
        src_dir = f"{label_root}/{sub}"
        if not os.path.isdir(src_dir):
            continue
        dst_dir = f"{LOCAL_ROOT}/{label}/{sub}"
        os.makedirs(dst_dir, exist_ok=True)
        files = sorted(glob.glob(f"{src_dir}/*"))[:CAP_PER_FOLDER]
        for f in files:
            shutil.copy2(f, dst_dir)
        print(f"{label}/{sub}: copied {len(files)}")
```

*Expect:* one `<label>/<sub>: copied N` line per subfolder (e.g. `real/cifake_real: copied
3000`), still takes several minutes since it's reading from the same slow Drive mount — just
bounded instead of unbounded. If you want to double-check progress without interrupting it,
run `!find /content/data/l1_aigen -type f | wc -l` in a **separate** cell and confirm the count
is climbing.

If you're confident the Drive-side dataset hasn't grown past what §3 should have produced, the
plain `cp -r` version below is simpler — but the bounded version above is the safer default:

```python
%cd /content/TruthPixel/ml
import datetime

# Copy the dataset to local disk once per session — reading from Drive directly is much
# slower than local /content for many small files (see note above). Use the bounded
# per-subfolder copy above instead if the Drive-side dataset has grown larger than expected.
!mkdir -p /content/data/l1_aigen
!cp -r /content/drive/MyDrive/TruthPixel/data/l1_aigen/* /content/data/l1_aigen/

RUN_ID = datetime.datetime.now().strftime("run_%Y%m%d_%H%M")
OUTPUT_DIR = f"/content/drive/MyDrive/TruthPixel/checkpoints/l1_aigen/{RUN_ID}"
print(RUN_ID)   # note this down — you'll reference it in §6 and later when wiring the backend

!python -m layer1_aigen.train \
    --data-root /content/data/l1_aigen \
    --output-dir {OUTPUT_DIR} \
    --device cuda \
    --epochs 5 \
    --batch-size 32 \
    --heldout-generators midjourney,sdxl,flux
```

*Expect:* the `cp` step itself still reads from the slow Drive mount (that's its source), so
budget a few minutes for a few-thousand-image dataset, not seconds — it prints nothing while
running and nothing on success. This is a one-time-per-session cost, versus paying that same
per-file overhead on *every epoch* if you train directly against Drive, so it's still a net win.
If you want to confirm it's progressing rather than stuck, run
`!find /content/data/l1_aigen -type f | wc -l` in another cell and check the count is climbing.
Then one JSON line per epoch (`{"epoch": 1, "train": {...}, "val": {...}}`),
with epoch 1 taking noticeably longer than the rest (first CLIP forward pass warms up caches),
then a final save with nothing printed. (Using a timestamped `--output-dir` per run rather than
a fixed path — see §8 for why; `--data-root` is local on purpose, see the I/O note above.)

What lands on Drive when this finishes (see `ml/layer1_aigen/train.py` / `model.py`):
- `l1_clip_head.pt` — the trained head weights + full run metadata
- `l1_clip_head.metadata.json` — same metadata, human-readable
- `history.json` — per-epoch train/val loss & accuracy

Screenshot augmentation (resize/JPEG-recompress/crop/blur — see ML_PLAN.md §1) is already
wired into the training loader (`ScreenshotAugmentor` in `train.py`) — you don't do anything
extra for it; it applies automatically to every training batch.

### 5.1 Known limitation — checkpoint only saves at the very end

`train.py` currently writes `l1_clip_head.pt` **once, after all epochs complete** — there's no
per-epoch checkpointing yet. If Colab disconnects mid-run (idle timeout ~90 min, hard cap
~12h on free tier), you lose that run's progress, not any data.

Because only the small head is trained (CLIP itself is frozen — no backprop through it),
epochs are fast even on T4, so the practical mitigation is: **keep `--epochs` modest (3–8) and
`--data-root` sized so one full run comfortably finishes inside a single session** — a few
thousand images at batch-size 32 trains in low tens of minutes, not hours. If you outgrow
that, the real fix is a small patch adding periodic checkpoint saves + a `--resume` flag to
`train.py`/`model.py` — flag this as a follow-up if training sets grow past a single-session
budget; not needed yet.

### 5.2 Freeing GPU memory left over from Cell 7 (SDXL)

`StableDiffusionXLPipeline` loads a UNet, VAE, and two text encoders onto the GPU — easily
10+ GB resident on a T4 in fp16. Colab doesn't free that just because a later cell stops
referencing `pipe` by name; PyTorch's CUDA allocator holds onto it until you explicitly release
it. If Cell 9 immediately follows Cell 7 in the same runtime, you'll typically see
`torch.OutOfMemoryError` on the very first training batch, with a large "memory in use" figure
that doesn't match anything `--batch-size 32` should need.

Two ways to fix it, pick whichever you're already doing:

- **If Cell 7 already ran without the cleanup snippet in §3.4:** Runtime → **Restart session**
  (not "Restart and run all" — your data is already safe on Drive, no need to re-download
  anything), then re-run Cell 1 (mount Drive), Cell 2 (clone + install), and Cell 9 (train).
- **Going forward:** the cleanup lines now included at the end of Cell 7 (`del pipe`,
  `gc.collect()`, `torch.cuda.empty_cache()`) handle this automatically — run Cell 7 once with
  that cleanup in place and Cell 9 afterward should have the GPU free.

Quick way to confirm which situation you're in before debugging further: `!nvidia-smi` in a
scratch cell — if it shows several GB already "used" before Cell 9 even starts, that's this,
not a batch-size problem.

---

## 6. Evaluate — the honest, held-out-generator number

**Cell 10 — Evaluate.** Loads the checkpoint Cell 9 just wrote, re-runs it against the `test`
split under four perturbation variants (`pristine`, `jpeg_q75`, `screenshot_sim`,
`social_roundtrip` — the robustness matrix from ML_PLAN.md §4), and writes AUROC + accuracy per
variant to `eval_report.json`.

```python
# Reuses OUTPUT_DIR / RUN_ID from §5 if you're still in the same notebook session.
# If you're resuming later, set RUN_ID manually to the run_<timestamp> folder you want to evaluate.
!python -m layer1_aigen.eval \
    --data-root /content/drive/MyDrive/TruthPixel/data/l1_aigen \
    --checkpoint {OUTPUT_DIR}/l1_clip_head.pt \
    --report-path {OUTPUT_DIR}/eval_report.json \
    --device cuda \
    --heldout-generators midjourney,sdxl,flux
```

`eval.py` already runs the full robustness matrix from ML_PLAN.md §4 — `pristine`, `jpeg_q75`,
`screenshot_sim`, `social_roundtrip` — and reports AUROC + accuracy per variant, per the held-out
split. **Quote the held-out-generator, screenshot_sim number as the headline metric, not the
pristine same-distribution one** (ML_PLAN.md §4 — "never quote same-generator numbers as the
headline").

*Expect:* no live progress output until it finishes (it's just a forward-pass loop, no epochs),
then the function returns/prints the full metrics dict if you also do `print(result)` in the
cell. `eval_report.json` lands on Drive next to the checkpoint — that's your artifact to
reference in any write-up or demo.

---

## 7. What happens with the trained checkpoint (and why your laptop still doesn't need a GPU)

`backend/app/analyzers/l1_aigen.py` is **already wired** to load a real checkpoint — this is
not a follow-up anymore. It reads two settings (`backend/app/config.py`):

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| `l1_model_path` | `L1_MODEL_PATH` | `""` (empty → stub mode) | Path to a `l1_clip_head.pt` file, e.g. one of Cell 9's `run_<...>/l1_clip_head.pt` outputs |
| `l1_model_device` | `L1_MODEL_DEVICE` | `"auto"` (picks `cuda` if available, else `cpu`) | Force `cpu` or `cuda` explicitly if you want |

To point the backend at a checkpoint you trained in this doc:

1. Download that run's `l1_clip_head.pt` from Drive to wherever the backend runs (your laptop,
   or wherever it's deployed) — this is the *one* file that leaves Drive; it's a few MB (just
   the small head's weights), not a dataset.
2. Set `L1_MODEL_PATH=/path/to/l1_clip_head.pt` in `backend/.env` (see `.env.example`).
3. Leave `L1_MODEL_DEVICE=auto` (or explicitly `cpu` on a GPU-less laptop) — the analyzer will
   pick CPU automatically when no CUDA device is present.
4. Restart the backend. `L1_MODEL_PATH` unset (the default) keeps returning the neutral stub
   signal (`score=0.5, confidence=0.1`) — that's the current out-of-the-box behavior with no
   checkpoint configured, and it's what every claim gets until you do steps 1–3.

**Known mismatch to watch for:** `.env.example` currently has a `L1_DEVICE` key, but the actual
setting pydantic-settings binds to is `L1_MODEL_DEVICE` (per the table above) — `L1_DEVICE` on
its own is silently ignored (`extra="ignore"` in `Settings`). Use `L1_MODEL_DEVICE` if you want
to override the `auto` default; don't rely on `.env.example`'s current key name for that one.

For inference (as opposed to training), CLIP ViT-L/14 forward passes run acceptably on CPU for
low-volume dev/demo use (roughly 1–3s/image) — you do **not** need a GPU on your laptop just to
*use* the trained head locally, `L1_MODEL_DEVICE=auto` already falls back to `cpu` there. If/when
volume grows past that, [ML_PLAN.md](ML_PLAN.md) §6 already covers the answer: serverless GPU
inference (Modal/RunPod, scale-to-zero) in Phase 1 — same reasoning as "don't buy an always-on
GPU box for an async, bursty workload."

---

## 8. Run versioning — don't silently overwrite past runs

`train.py --output-dir` is just a folder path — nothing about the script itself timestamps or
namespaces runs. If you point two different runs at the same `--output-dir`, the second run's
`l1_clip_head.pt` **silently replaces** the first (plain `torch.save` overwrite, no warning).
That's fine for quick iteration but loses your comparison history.

Convention used throughout this doc: **one Drive subfolder per run**, named
`run_<YYYYMMDD_HHMM>` (generated automatically in the §5 snippet). This gets you, for free:

- Every experiment's checkpoint, metadata, history, and eval report kept side-by-side on Drive.
- A simple way to compare runs — `metadata.json` + `eval_report.json` are both small JSON files,
  easy to `cat`/diff across `run_*` folders.
- A clear answer to "which checkpoint is currently wired into the backend" (§7) — record the
  exact `run_<...>` path in whatever config/settings ends up pointing at it, not just
  "the latest one."

Keep a lightweight running log — a single Drive text file works fine, no tooling needed.

**Cell 11 — Log the run.** Appends one line per run to a plain-text log on Drive — run this
right after Cell 10 (eval) so you have both the run's config and a pointer to its results in
one place. No dependencies, no tooling.

```python
log_line = f"{RUN_ID}\tepochs={5}\theldout=midjourney,sdxl,flux\tdata_root=data/l1_aigen\n"
with open("/content/drive/MyDrive/TruthPixel/checkpoints/l1_aigen/runs.log", "a") as f:
    f.write(log_line)
```

*Expect:* no output; `!cat /content/drive/MyDrive/TruthPixel/checkpoints/l1_aigen/runs.log`
should show one line per training run you've ever done, oldest first.

## 9. Resuming in a brand-new Colab session

Everything that matters survived the last session's disconnect — it's on Drive. To pick back up
(new day, new Colab runtime, doesn't matter):

1. Open `TruthPixel/notebooks/TruthPixel_L1_Training.ipynb` from Drive (not a fresh notebook —
   reuse it so your cells/history stay intact).
2. Runtime → Change runtime type → confirm **T4 GPU** is still selected (Colab sometimes resets
   this on a new session).
3. Re-run §2.2 (mount Drive) and §2.3 (clone repo + `pip install`) — both are cheap and
   idempotent; re-cloning just overwrites `/content/TruthPixel` with the same thing.
4. Re-run §4 (dataset sanity check) to confirm Drive data is still where you left it.
5. Decide: **new run** (fresh `RUN_ID`, §5 as written) or **continue evaluating an old run**
   (skip §5, jump to §6 with `RUN_ID` set manually to the folder name from `runs.log`, §8).

There is currently no `--resume`-from-checkpoint flag (§5.1) — "resuming" here means resuming
your *workflow*, not resuming a partially-trained model. A new run always starts the head from
a fresh random init.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `discover_samples` returns 0 (§4) | Folder layout doesn't match `real/`/`generated/<generator>/` exactly, or Drive hasn't finished mounting/syncing | Re-check §3's tree; `!ls` the Drive path directly to confirm files are actually there before debugging the dataset code |
| `RuntimeError: Training split is empty` | All samples landed in `val`/`test` by chance, or `--heldout-generators` matches every generator folder you have | Add more real data, or drop `--heldout-generators` down to only the buckets you actually intend to hold out |
| `CUDA out of memory` on the very first training batch, after running Cell 7 (SDXL) earlier in the session | Leftover SDXL pipeline still resident on the GPU (10+ GB) — not a batch-size issue at all | See §5.2: Runtime → Restart session (data's already on Drive), then re-run Cells 1, 2, 9. Going forward, Cell 7's cleanup snippet (`del pipe` + `empty_cache()`) prevents this |
| `CUDA out of memory` with no SDXL run earlier in the session | `--batch-size` genuinely too high for T4's ~15 GB, usually from a very large image mixed into the batch | Lower `--batch-size` (try 16 or 8); confirm no giant/corrupt images slipped into `data/l1_aigen` |
| `RuntimeError: Dataset scripts are no longer supported` | `datasets>=3.0` (Colab's default) refuses to run any HF community dataset's custom loading script — hits any script-based dataset, not just DiffusionDB | Add `revision="refs/convert/parquet"` to `load_dataset(...)` (§3.2's fix); if that config wasn't auto-converted at all, pin `datasets==2.19.0` + `trust_remote_code=True` instead (restart runtime first) |
| `ValueError: BuilderConfig '<name>' not found. Available: ['default']` | The `refs/convert/parquet` mirror only kept a single `"default"` config, not the dataset's original per-size config names (`2m_random_5k` etc.) | Use `"default"` as the config name, add `streaming=True`, and take a random slice with `.shuffle(...).take(N)` instead of relying on a pre-sized config (§3.2's fix) — `"default"` is usually the full dataset, too big to load whole |
| Kaggle download 403/401 | `kaggle.json` missing, stale, or `KAGGLE_CONFIG_DIR` pointed at the wrong folder | Re-check §2.1; confirm `os.environ["KAGGLE_CONFIG_DIR"]` matches where `kaggle.json` actually is on Drive |
| `datasets` HF download fails on a config name | HF renamed/removed that subset config | Check the dataset card on huggingface.co for current config names before re-running §3.2 |
| Colab disconnects mid-training | Free-tier idle timeout (~90 min) or session cap (~12h) | See §5.1 — keep runs sized to finish in one sitting; nothing before the run's final save is recoverable |
| Training "Executing" for 15+ minutes with no epoch output, GPU RAM flat/not climbing | Reading images directly from the Drive mount — slow per-file network round-trips, not GPU compute | Interrupt, `cp` the dataset to `/content/data/l1_aigen` (local disk), rerun with `--data-root` pointed there (§5's code block already does this) |
| The local-copy `cp -r` itself is taking far longer than expected (many minutes, file count still climbing well past what §3 should have produced) | Drive-side dataset has accumulated more files than intended — e.g. an earlier uncapped run of a cell left extra files that a later, smaller-capped re-run never removed | Compare `find <drive-path> -type f \| wc -l` vs. the local copy's count (§5); if source is much bigger than expected, use the bounded per-subfolder copy in §5 instead of `cp -r` |
| Local file count keeps climbing well past the bounded script's max (e.g. `CAP_PER_FOLDER=3000` × a handful of subfolders should cap around 12-15k, but `find` shows 80k+) even after switching to the bounded copy | **Interrupting a `!shell` cell in Colab does not reliably kill the underlying subprocess** — an earlier `cp -r` you thought you stopped can keep running in the background, writing into the same folder concurrently with whatever you run next | `rm -rf /content/data/l1_aigen` alone isn't enough if the stray process is still alive and will just refill it. **Runtime → Restart session** (data's all on Drive, nothing lost) to guarantee it's actually dead, then re-run Cells 1, 2, the `rm -rf`/`mkdir -p`, and the bounded copy fresh |
| `google.colab.drive.mount` hangs or fails | Browser popup for Google auth blocked, or Drive quota/permissions issue | Retry in a fresh cell; check Drive storage quota isn't full (§11 has typical footprint) |
| Training "succeeds" but accuracy stays ~50% | Class imbalance, near-duplicate real/generated images, or too few epochs for the head to converge | Check `summarize_assignments` output (§4) for balance; inspect `history.json` — if train accuracy also stays flat, the issue is data, not training length |

## 11. Time & cost estimates

Rough, free-tier T4 numbers — actual timing depends on dataset size and image resolution:

| Step | Time | Notes |
|---|---|---|
| Repo clone + `pip install` | ~1 min | Every session |
| CIFAKE download + reshape (§3.1) | ~5 min | One-time bootstrap |
| DiffusionDB 5k-image pull (§3.2) | ~10–20 min | Network-bound, mostly image decode/save |
| SDXL held-out bucket, ~200 images (§3.4) | ~10–15 min | A few seconds per image on T4 |
| `train.py`, 5 epochs, few-thousand-image dataset | ~15–40 min | Only the head backprops — CLIP forward pass dominates |
| `eval.py`, full robustness matrix | ~5–15 min | 4 perturbation variants × test-set size |
| **Total for one full first pass** | **~1–2 hours** | Comfortably inside one free Colab session |

Cost: **$0** on the free tier for this model. Colab Pro ($10-ish/mo) or Pro+ only becomes
worth it if you outgrow a single 90-min-idle / 12h-cap session, or want faster GPUs — not
needed for T1 as scoped. Google Drive free tier (15 GB) comfortably holds a few-thousand-image
dataset plus several `run_*` checkpoint folders (each run's artifacts are tens of MB, not GB —
the checkpoint is just a small MLP head's weights).

---

## 12. Checklist

- [x] Notebook created and saved to Drive as `TruthPixel/notebooks/TruthPixel_L1_Training.ipynb`
- [x] `kaggle.json` uploaded to Drive (or skip, use HF-only path)
- [x] Drive folders created (`notebooks/`, `data/l1_aigen/{real,generated}`, `checkpoints/l1_aigen`)
- [x] Colab runtime set to T4 GPU
- [x] Repo cloned + `ml/requirements.txt` installed (per session)
- [x] CIFAKE bootstrap copied in (Cell 4, capped at 2,000/class) — still need a short `train.py` run to confirm dataset discovery end-to-end
- [ ] Real training subset in Drive — DiffusionDB pull done (Cell 5, `streaming=True` + `"default"` fix, 5k images); product-photo real side (Cell 6) still pending
- [ ] Held-out generator bucket present (SDXL self-gen or a genuinely unseen-generator slice)
- [ ] `train.py` run completes inside one session, using a timestamped `run_<...>` output dir (§8); checkpoint + metadata + history land on Drive
- [ ] Run recorded in `checkpoints/l1_aigen/runs.log` (§8)
- [ ] `eval.py` run produces `eval_report.json`; held-out `screenshot_sim` AUROC recorded as the headline number
- [ ] Chosen `run_<...>/l1_clip_head.pt` downloaded from Drive and pointed to via `L1_MODEL_PATH` in the backend's `.env` (§7 — the analyzer is already wired, this is just config)
