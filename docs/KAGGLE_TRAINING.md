# Training on Kaggle Notebooks (alternative to Colab)

> Same goal as [COLAB_TRAINING.md](COLAB_TRAINING.md) — train T1 (the L1 CLIP head) with no
> local GPU and no dataset downloads to your laptop — but on Kaggle's free GPU tier instead of
> Colab's. Use this doc if Colab's daily GPU quota runs out, or if you just prefer Kaggle.
> Part of the TruthPixel doc suite: [ML_PLAN.md](ML_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COLAB_TRAINING.md](COLAB_TRAINING.md) · [ROADMAP.md](ROADMAP.md)

## Contents

0. [What this covers](#0-what-this-covers)
1. [Kaggle vs. Colab — the mental model](#1-kaggle-vs-colab--the-mental-model)
2. [One-time setup (do these before touching any cell)](#2-one-time-setup-do-these-before-touching-any-cell)
3. [Cell-by-cell guide](#3-cell-by-cell-guide)
4. [Persisting the checkpoint](#4-persisting-the-checkpoint)
5. [Troubleshooting](#5-troubleshooting)
6. [Time & cost estimates](#6-time--cost-estimates)
7. [Full checklist](#7-full-checklist)

---

## 0. What this covers

Only T1 — the L1 CLIP-head (frozen `open_clip` ViT-L/14 + a small trainable MLP head). Same
code as Colab: `ml/layer1_aigen/{dataset,augment,model,train,eval}.py`, unmodified. This doc is
purely about running it on **Kaggle Notebooks** — different storage model, different GPU quota,
different data-attach flow. Everything else is identical to Colab.

**Notebook name:** `truthpixel-l1-training` — Kaggle slugs are lowercase-hyphenated.
Create it fresh at kaggle.com/code → "New Notebook" if starting from scratch.

**Resetting between runs:** if you're restarting a failed or incomplete training from scratch,
kill the kernel (Session → Stop) and then in any cell run:

```python
import shutil, os
shutil.rmtree("/kaggle/working/data", ignore_errors=True)
shutil.rmtree("/kaggle/working/checkpoints", ignore_errors=True)
print("Cleaned. Ready to re-run Cells 2-7.")
```

This wipes only the data/checkpoint dirs — the cloned repo (`/kaggle/working/TruthPixel`) stays
so Cell 1 re-clone can be skipped unless you need a fresh `git pull`.

---

## 1. Kaggle vs. Colab — the mental model

| Concept | Colab | Kaggle |
|---|---|---|
| Ephemeral compute disk | `/content/` | `/kaggle/working/` |
| Persistent storage | Google Drive, mounted, read/write | **Kaggle Datasets** — read-only "Input" attached in the notebook UI, or your own dataset you push output to |
| How you get data in | Download inside the session, write to Drive | **"Add Input"** in sidebar UI to attach a public/private Kaggle Dataset (zero download code), or HF streaming fallback |
| Speed of reading data | Drive mount is slow (FUSE, per-file network round-trip) — copy to `/content/` first | `/kaggle/input/` is fast local-equivalent storage — **no copy step needed** |
| How checkpoints survive | Already on Drive, nothing to do | Must commit ("Save Version → Save & Run All") or push to a Kaggle Dataset explicitly |
| GPU quota | ~12h cap per session, informal daily limits | **30 GPU-hours per week**, per-session cap ~9–12h, phone verification required |

**The practical upshot on Kaggle:**
- Reading from `/kaggle/input/...` is fast — no "copy off the mount" workaround needed.
- But `/kaggle/working` is wiped when a fresh session starts — commit or push before closing.
- Multiple browser tabs open on the same kernel cause `ConcurrencyViolation` / "Failed to save
  draft" errors. **Keep exactly one tab** open at all times.

---

## 2. One-time setup (do these before touching any cell)

### 2.1 Phone verification (required for GPU — easy to miss)

Kaggle → Account → Settings → **Phone Verification**. Without this, the GPU option is entirely
greyed out in the notebook Settings panel. Takes 2–3 minutes. Do it before anything else.

### 2.2 Create or open the notebook

- New notebook: kaggle.com/code → **"New Notebook"** → name it `truthpixel-l1-training`.
- Resuming: open the existing notebook. If you have it open in two tabs, **close one** — two
  tabs on the same kernel cause racing autosave conflicts (`ConcurrencyViolation` errors that
  look unrelated to anything you did).

### 2.3 Turn on Internet access

Notebook editor → right sidebar → **Settings** → **Internet: On**. Default is off. Required for
`pip install`, `git clone`, and Hugging Face streaming downloads. Do this before running Cell 1.

### 2.4 Select the GPU accelerator

Notebook → Settings → **Accelerator → GPU T4 x2** (or P100 if T4 isn't offered). Kaggle bills
wall-clock session GPU-time, not per-device, so T4 x2 does not burn twice your weekly quota for
having two devices.

### 2.5 Attach CIFAKE as a notebook Input (UI action — must happen before Cell 2)

> **This is the most common mistake.** The CIFAKE dataset cannot be attached with code — it must
> be added through the notebook's Input panel in the UI. If you skip this, Cell 2 fails
> immediately with `FileNotFoundError` even though the code is correct.

In the notebook editor, **right sidebar → "Add Input"** → make sure the **"Datasets"** tab/filter
is selected (not "Notebooks" or "Models" — picking a notebook by mistake is the second most
common trap here) → search **"cifake"** → find **"CIFAKE: Real and AI-Generated Synthetic
Images"** by **Jordan J. Bird** (aka birdy654), 120000 files / 110 MB → click the **`+`** to add
it. It shows up under a **"DATASETS"** heading in the sidebar once correctly attached (if it
shows under "NOTEBOOKS" instead, you added the wrong item — remove it and redo this step).

**Known quirk (confirmed in practice, 2026-07-10): the mount path is not always the flat
`/kaggle/input/<dataset-slug>/` you'd expect.** Kaggle mounted CIFAKE nested as
`/kaggle/input/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images/{train,test}/` —
not the flat path. Don't hardcode either path — verify with a recursive search instead of a
plain `os.listdir`:

```python
import glob
print("REAL dirs:", glob.glob("/kaggle/input/**/REAL", recursive=True))
print("FAKE dirs:", glob.glob("/kaggle/input/**/FAKE", recursive=True))
```

You should see at least one path in each list (e.g.
`/kaggle/input/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images/train/REAL`, or
the flatter `/kaggle/input/cifake-real-and-ai-generated-synthetic-images/train/REAL` — both are
fine, the recursive glob finds either). If both lists are empty:
- Confirm the sidebar shows it under "DATASETS", not "NOTEBOOKS".
- Try a full session restart (Session menu → **Stop Session**, then reopen the notebook) — a new
  Input attached mid-session doesn't always mount into an already-running kernel; a full
  stop/reopen mounts it more reliably than staying in the same session.

---

## 3. Cell-by-cell guide

### Cell 1 — Clone repo & install training deps

Pulls the TruthPixel code into the ephemeral working environment and installs what
`ml/layer1_aigen/` needs. Kaggle's base image already has `torch`/`torchvision` with CUDA, so
this mostly just adds `open_clip_torch` and any other missing deps.

```python
import os

REPO = "/kaggle/working/TruthPixel"

if not os.path.exists(REPO):
    os.system("git clone https://github.com/thanoban/TruthPixel.git " + REPO)
else:
    print("Repo already cloned — pulling latest.")
    os.system(f"cd {REPO} && git pull")

os.chdir(f"{REPO}/ml")

# Selective installs: avoid downgrading Kaggle's pinned numpy/torch
os.system("pip install -q open_clip_torch datasets accelerate diffusers")
print("Done.")
```

*Expect:* "Cloning into..." or "Already up to date.", then pip install lines with no `ERROR:`.

---

### Cell 2 — Reshape CIFAKE into the expected layout

**Prerequisite: CIFAKE must be attached as a notebook Input (§2.5) before running this cell.**

This cell reshapes the CIFAKE dataset (which has `REAL` and `FAKE` subdirs somewhere under
`/kaggle/input`) into the layout that `ml/layer1_aigen/dataset.py::discover_samples` expects:

```
data/l1_aigen/
├── real/cifake_real/        ← real photos
└── generated/cifake/        ← AI-generated
```

Capped at 3,000 per class so a bootstrap training set stays manageable.

**Uses a recursive glob for `REAL`/`FAKE` folders, not a top-level-folder-name match.** An
earlier version of this cell matched on `"cifake" in folder_name`, which broke the first time
this was actually run — Kaggle mounted the dataset nested as
`/kaggle/input/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images/...` instead of
the flat `/kaggle/input/cifake-real-and-ai-generated-synthetic-images/...` the old code assumed.
Searching for the `REAL`/`FAKE` leaf folders directly, recursively, sidesteps the mount-path
question entirely — it works regardless of nesting depth or naming.

```python
import os, shutil, glob

DST = "/kaggle/working/data/l1_aigen"
CAP = 3000

os.makedirs(f"{DST}/real/cifake_real", exist_ok=True)
os.makedirs(f"{DST}/generated/cifake", exist_ok=True)

# Recursive search — works regardless of mount nesting (flat or /kaggle/input/datasets/<owner>/...)
real_dirs = sorted(glob.glob("/kaggle/input/**/REAL", recursive=True))
fake_dirs = sorted(glob.glob("/kaggle/input/**/FAKE", recursive=True))
print("REAL dirs found:", real_dirs)
print("FAKE dirs found:", fake_dirs)

if not real_dirs or not fake_dirs:
    raise FileNotFoundError(
        "CIFAKE REAL/FAKE folders not found anywhere under /kaggle/input.\n"
        "UI action required (cannot be done in code):\n"
        "  Right sidebar -> Add Input -> Datasets tab -> search 'cifake' -> add Jordan J. Bird's dataset.\n"
        "If already added, try Session menu -> Stop Session, then reopen the notebook\n"
        "(newly attached inputs don't always mount into an already-running kernel).\n"
        "Then re-run this cell."
    )

# Prefer a 'train' split path if multiple matches exist (CIFAKE also has a smaller 'test' split)
def _prefer_train(paths):
    train_paths = [p for p in paths if "/train/" in p.replace("\\", "/")]
    return train_paths[0] if train_paths else paths[0]

real_src = _prefer_train(real_dirs)
fake_src = _prefer_train(fake_dirs)
print(f"Using REAL: {real_src}")
print(f"Using FAKE: {fake_src}")

real_files = sorted(glob.glob(f"{real_src}/*"))[:CAP]
fake_files = sorted(glob.glob(f"{fake_src}/*"))[:CAP]

if not real_files or not fake_files:
    raise FileNotFoundError(
        f"REAL/FAKE folders found but empty: {real_src} ({len(real_files)} files), "
        f"{fake_src} ({len(fake_files)} files). Check the dataset actually finished mounting."
    )

real_dst = f"{DST}/real/cifake_real"
fake_dst = f"{DST}/generated/cifake"

# Skip files already copied (idempotent re-run)
already_real = len(os.listdir(real_dst))
already_fake = len(os.listdir(fake_dst))

print(f"Already copied: {already_real} real, {already_fake} fake. Topping up to {CAP}.")

copied_r = copied_f = 0
for f in real_files[already_real:]:
    shutil.copy2(f, real_dst)
    copied_r += 1
for f in fake_files[already_fake:]:
    shutil.copy2(f, fake_dst)
    copied_f += 1

total_r = len(os.listdir(real_dst))
total_f = len(os.listdir(fake_dst))
print(f"Copied this run: {copied_r} real, {copied_f} fake")
print(f"Total: {total_r} real, {total_f} fake")

if total_r < CAP or total_f < CAP:
    print(f"WARNING: fewer than {CAP} files — check CIFAKE structure above.")
```

*Expect:* `Total: 3000 real, 3000 fake` within well under a minute — Kaggle's input mount is
fast local-equivalent storage, not a network FUSE mount.

---

### Cell 3 — Pull DiffusionDB via Hugging Face streaming

**Check Kaggle Datasets first** (search "AI generated images" / "GenImage" / "diffusion images"
on kaggle.com/datasets) — if a ready-made dataset exists, **Add Input** it and reshape with a
Cell-2-style script instead of using the streaming pull below.

The streaming pull is the fallback when no Kaggle-native dataset fits. The
`revision="refs/convert/parquet"` and `streaming=True` fix is required — `datasets>=3.0` refuses
DiffusionDB's community loading script, same as Colab (see COLAB_TRAINING.md §10 for the error
messages and full explanation).

```python
from datasets import load_dataset
import os

DST = "/kaggle/working/data/l1_aigen/generated/diffusiondb"
CAP = 3000
os.makedirs(DST, exist_ok=True)

already = len(os.listdir(DST))
if already >= CAP:
    print(f"Already have {already} diffusiondb images — skipping.")
else:
    ds = load_dataset(
        "poloclub/diffusiondb", "default", split="train",
        revision="refs/convert/parquet", streaming=True,
    )
    ds = ds.shuffle(seed=42, buffer_size=1000)
    needed = CAP - already
    for i, row in enumerate(ds.take(needed)):
        row["image"].convert("RGB").save(f"{DST}/{already + i:05d}.jpg", quality=92)
    print(f"Done. Total diffusiondb: {len(os.listdir(DST))}")
```

*Expect:* no upfront progress bar (streaming — data fetched lazily), then a save loop that runs
a few minutes. Each image is fetched on demand; overall ~5–15 min for 3,000 images.

**Known errors:**
- `RuntimeError: Dataset scripts are no longer supported` → add `revision="refs/convert/parquet"`
- `ValueError: BuilderConfig '2m_random_5k' not found` → use `"default"` config, not a named subset
- Both fixes are already in the cell above.

---

### Cell 4 — Real (non-AI) product-photo side

Streams from COCO validation set as a diverse real-world photo fallback. If you find a
Kaggle-native product-photo dataset, **Add Input** it and replace this cell with a reshape.

```python
from datasets import load_dataset
import os

DST = "/kaggle/working/data/l1_aigen/real/coco_fallback"
CAP = 3000
os.makedirs(DST, exist_ok=True)

already = len(os.listdir(DST))
if already >= CAP:
    print(f"Already have {already} coco images — skipping.")
else:
    ds = load_dataset("detection-datasets/coco", split="val", streaming=True)
    needed = CAP - already
    for i, row in enumerate(ds.take(needed)):
        row["image"].convert("RGB").save(f"{DST}/{already + i:05d}.jpg", quality=92)
    print(f"Done. Total coco_fallback: {len(os.listdir(DST))}")
```

---

### Cell 5 — Generate held-out SDXL bucket

Self-generate on the Kaggle GPU using a real prompt list — 20+ damage-plausible prompts. A
too-small list makes the held-out eval in Cell 8 meaningless. The `del pipe` / `empty_cache()`
cleanup at the end is **required** — leftover SDXL GPU memory (~10+ GB) will cause OOM during
training in Cell 7.

```python
import os, torch, gc
from diffusers import StableDiffusionXLPipeline

DST = "/kaggle/working/data/l1_aigen/generated/sdxl"
os.makedirs(DST, exist_ok=True)

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
    "a water-damaged cardboard box, product photo",
    "a burned fabric sleeve, product photo",
    "a cracked phone case back, product photo",
    "a torn book cover, product photo",
    "a rust-stained stainless steel sink, product photo",
]

existing = len(os.listdir(DST))
print(f"Already have {existing} SDXL images. Generating {len(prompts) - existing} more.")

if existing < len(prompts):
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16
    ).to("cuda")

    for i, p in enumerate(prompts[existing:], start=existing):
        img = pipe(p).images[0]
        img.save(f"{DST}/{i:04d}.jpg", quality=92)

    print("Cleaning up SDXL pipeline...")
    del pipe
    gc.collect()
    torch.cuda.empty_cache()

print(f"Total SDXL images: {len(os.listdir(DST))}")
```

*Expect:* model-download progress bar the first time (~5 min), then one image per prompt (~20–40s
each). Total ~15–30 min for 25 prompts. After cleanup, GPU memory should drop from ~12 GB to
near-baseline.

---

### Cell 6 — Dataset sanity check

Verify the layout before committing GPU time to training. `discover_samples` will return 0 if
any path or folder name is wrong.

```python
import os
os.chdir("/kaggle/working/TruthPixel/ml")

from layer1_aigen.dataset import discover_samples, assign_splits, summarize_assignments

DATA_ROOT = "/kaggle/working/data/l1_aigen"
samples = discover_samples(DATA_ROOT)
print(f"Total samples discovered: {len(samples)}")

assignments = assign_splits(samples, heldout_generators={"sdxl", "midjourney", "flux"})
print(summarize_assignments(assignments))
```

*Expect:* total ≥ 9,000 (3k real/cifake + 3k generated/cifake + 3k generated/diffusiondb, plus
any SDXL). Non-zero counts in every split. If anything is 0, check the folder layout at
`/kaggle/working/data/l1_aigen/` — the expected structure is `real/<name>/*.jpg` and
`generated/<name>/*.jpg`.

---

### Cell 7 — Train

Reads data directly from `/kaggle/working/data/l1_aigen` (fast local NVMe — no copy step needed,
unlike Colab). Output checkpoint lands in `/kaggle/working/checkpoints/`. **Commit before closing
the session** (§4) — this dir is wiped on a fresh start.

```python
import os, datetime
os.chdir("/kaggle/working/TruthPixel/ml")

RUN_ID = datetime.datetime.now().strftime("run_%Y%m%d_%H%M")
OUTPUT_DIR = f"/kaggle/working/checkpoints/l1_aigen/{RUN_ID}"
print(f"Run ID: {RUN_ID}")
print(f"Output: {OUTPUT_DIR}")

os.system(f"""python -m layer1_aigen.train \
    --data-root /kaggle/working/data/l1_aigen \
    --output-dir {OUTPUT_DIR} \
    --device cuda \
    --epochs 5 \
    --batch-size 32 \
    --heldout-generators midjourney,sdxl,flux
""")
```

*Expect:* one `{"epoch": N, "train": {...}, "val": {...}}` JSON line per epoch. ~15–40 min for 5
epochs on ~9k images on a T4. If the cell appears "executing" with no output for >5 min and GPU
utilization is flat, check Cell 5's cleanup ran — leftover SDXL memory is the usual cause.

---

### Cell 8 — Evaluate

```python
import os, json
os.chdir("/kaggle/working/TruthPixel/ml")

# RUN_ID must match what Cell 7 printed — re-set if the kernel was restarted
# RUN_ID = "run_YYYYMMDD_HHMM"
OUTPUT_DIR = f"/kaggle/working/checkpoints/l1_aigen/{RUN_ID}"

os.system(f"""python -m layer1_aigen.eval \
    --data-root /kaggle/working/data/l1_aigen \
    --checkpoint {OUTPUT_DIR}/l1_clip_head.pt \
    --report-path {OUTPUT_DIR}/eval_report.json \
    --device cuda \
    --heldout-generators midjourney,sdxl,flux
""")

with open(f"{OUTPUT_DIR}/eval_report.json") as f:
    print(json.dumps(json.load(f), indent=2))
```

Robustness matrix: `pristine`, `jpeg_q75`, `screenshot_sim`, `social_roundtrip`. Quote the
held-out `screenshot_sim` AUROC as the headline number per ML_PLAN.md §4 — it's the honest
metric for field accuracy after screenshot evasion.

---

## 4. Persisting the checkpoint

**This step is the main Kaggle-vs-Colab difference.** On Colab, checkpoints land on Drive and
survive automatically. On Kaggle, `/kaggle/working` is wiped when a fresh session starts — you
must do one of the following before closing the session.

> **Confirmed the hard way (2026-07-10): "a fresh session" includes a session restart done to
> fix something unrelated, not just closing the browser tab.** A full training + eval run
> completed successfully (`run_20260709_2042`, 0.9688 held-out AUROC — see §7 checklist), but a
> **Session menu → Stop Session** restart done afterward (to troubleshoot an unrelated CIFAKE
> mount issue in the *same* notebook) silently wiped `/kaggle/working`, taking the trained
> checkpoint with it — even though the eval output text was still visible in the notebook's
> saved cell output, the underlying `.pt` file was gone. **Do Option A or B immediately after
> Cell 8 (evaluate) succeeds, before running anything else in that session** — don't treat
> persisting as a "do it before I close the tab" step, treat it as the very next cell after eval.

### Option A — Commit the notebook (simplest, one-off)

Click **Save Version** → **Save & Run All (Commit)**. Kaggle re-runs the full notebook and saves
`/kaggle/working`'s final state as the notebook's **Output**. The checkpoint is then downloadable
from the notebook's "Output" tab. Enough for a one-off run to grab `l1_clip_head.pt` and wire it
into the backend.

### Option B — Push to a private Kaggle Dataset (better for multi-run history)

Works like Colab's Drive: once the dataset exists, future sessions can **Add Input** it to pull a
previous checkpoint back in without re-training.

**Cell 9 — Push checkpoint to a private Kaggle Dataset.**

```python
import json, os

DATASET_DIR = "/kaggle/working/l1_checkpoint_release"
os.makedirs(DATASET_DIR, exist_ok=True)

os.system(f"cp {OUTPUT_DIR}/l1_clip_head.pt {DATASET_DIR}/")
os.system(f"cp {OUTPUT_DIR}/l1_clip_head.metadata.json {DATASET_DIR}/")

metadata = {
    "title": "TruthPixel L1 checkpoints",
    "id": "<your-kaggle-username>/truthpixel-l1-checkpoints",
    "licenses": [{"name": "CC0-1.0"}],
}
with open(f"{DATASET_DIR}/dataset-metadata.json", "w") as f:
    json.dump(metadata, f)

# First time creating the dataset — comment this out and uncomment the version
# line on subsequent runs
os.system(f"kaggle datasets create -p {DATASET_DIR}")
# os.system(f"kaggle datasets version -p {DATASET_DIR} -m 'run {RUN_ID}'")
```

*Expect:* `kaggle datasets create` prints a URL to your new private dataset. Future sessions can
**Add Input** it by searching your username in the sidebar.

### Wiring the checkpoint into the backend

Same as COLAB_TRAINING.md §7 — download `l1_clip_head.pt` from the notebook Output tab or your
Kaggle Dataset, place it at `backend/models/l1_clip_head.pt`, and set in `backend/.env`:

```
L1_MODEL_PATH=./models/l1_clip_head.pt
L1_MODEL_DEVICE=cpu   # or cuda if your inference host has a GPU
```

Restart the backend — `l1_aigen.py` loads the local checkpoint (mode 1) and skips the HF
ensemble fallback.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| GPU accelerator greyed out | Phone number not verified | §2.1 — account Settings → Phone Verification |
| `pip install` / `git clone` / HF download fails | Internet is off | §2.3 — Settings → Internet: On |
| Cell 2 fails: `FileNotFoundError: CIFAKE not found` | Dataset not attached as Input, or wrong item added (a Notebook instead of a Dataset) | §2.5 — UI action: right sidebar → Add Input → **Datasets tab** → search "cifake" → add Jordan J. Bird's dataset (must show under "DATASETS" in the sidebar, not "NOTEBOOKS") |
| `os.listdir("/kaggle/input")` returns `[]` or `['datasets']` (not the dataset name) | Either not attached yet, or attached but not mounted into the *current running* kernel session | Confirm it shows under "DATASETS" in the sidebar. If it does but still isn't visible to the kernel, do a full **Session menu → Stop Session**, then reopen the notebook — a soft restart isn't always enough for a newly attached Input to mount |
| `glob.glob("/kaggle/input/**/REAL", recursive=True)` returns `[]` even though the dataset shows as attached | Real symptom observed in practice: Kaggle nested the mount as `/kaggle/input/datasets/<owner>/<dataset>/...` instead of the flat `/kaggle/input/<dataset>/...` path | Cell 2 already searches recursively so this shouldn't matter — if it still returns empty, run `import subprocess; print(subprocess.run(["find", "/kaggle/input", "-maxdepth", "4"], capture_output=True, text=True).stdout)` to see the actual mount tree and check the dataset is fully synced, not still mounting |
| `RuntimeError: Dataset scripts are no longer supported` | `datasets>=3.0` refuses DiffusionDB loading script | Already fixed in Cell 3: `revision="refs/convert/parquet"` + `streaming=True` |
| `ValueError: BuilderConfig '2m_random_5k' not found` | Named subset doesn't exist in parquet mirror | Already fixed in Cell 3: use `"default"` config |
| Training cell runs but no output, GPU flat | Leftover SDXL pipeline from Cell 5 still resident | Check Cell 5's `del pipe` + `empty_cache()` ran. If not, restart kernel, re-run Cells 5-cleanup and 7 |
| `discover_samples` returns 0 | Folder layout mismatch | Verify `/kaggle/working/data/l1_aigen/real/<name>/*.jpg` and `generated/<name>/*.jpg` exist |
| Session ends and checkpoint is gone | `/kaggle/working` not committed | §4 — always Option A (commit) or Option B (push dataset) before closing |
| "You have exceeded your GPU quota" | 30 GPU-hour/week cap hit | Wait for weekly reset (shown in Settings → Accelerator), or switch to Colab if its quota reset |
| `ConcurrencyViolation` / "Failed to save draft" | Multiple browser tabs open on the same kernel | Close all but one tab — autosave races between tabs cause this |
| `kaggle datasets create` auth error | No `kaggle.json` available | Use Option A (commit) instead — no credential needed for that path |

---

## 6. Time & cost estimates

| Step | Typical time on T4 |
|---|---|
| Cell 1 — clone + install | ~2–4 min |
| Cell 2 — CIFAKE reshape (Kaggle-native, fast) | < 1 min |
| Cell 3 — DiffusionDB stream 3k images | ~10–20 min |
| Cell 4 — COCO stream 3k images | ~10–20 min |
| Cell 5 — SDXL generate 25 images | ~15–30 min |
| Cell 6 — sanity check | < 1 min |
| Cell 7 — train 5 epochs on ~9k images | ~20–40 min |
| Cell 8 — evaluate | ~5–15 min |
| **Total** | **~1–2 hours** |

Weekly quota consumed: ~1–2 of your 30 free GPU-hours. **Cost: $0** — this is Kaggle's free
tier, no relation to any Azure/GCP credit.

---

## 7. Full checklist

**Before any cell:**
- [ ] Phone number verified on your Kaggle account (§2.1)
- [ ] Notebook created or opened, **only one browser tab** open
- [ ] Internet turned on (Settings → Internet: On)
- [ ] GPU accelerator selected (T4 x2 preferred)
- [ ] **CIFAKE attached as Input via the UI sidebar** — `os.listdir("/kaggle/input")` shows the CIFAKE folder (§2.5)

**Cells:**
- [ ] Cell 1 — repo cloned, deps installed, no `ERROR:` lines
- [x] Cell 2 — `Total: 3000 real, 3000 fake` printed (confirmed 2026-07-10, nested mount path resolved via recursive glob)
- [ ] Cell 3 — DiffusionDB or Kaggle-native AI dataset pulled in
- [ ] Cell 4 — COCO fallback real photos pulled in
- [ ] Cell 5 — SDXL bucket generated with 20+ prompts; `del pipe` / `empty_cache()` confirmed
- [ ] Cell 6 — sanity check: total ≥ 9k samples, non-zero in every split
- [x] Cell 7 — training completes; epoch JSON lines printed (confirmed 2026-07-09, `run_20260709_2042`, 5 epochs, best val accuracy 0.8907 in the committed checkpoint metadata)
- [x] Cell 8 — `eval_report.json` printed; held-out `screenshot_sim` AUROC recorded — **0.9688 AUROC / 0.8959 accuracy** on held-out generators (sdxl, midjourney, flux), robustness matrix holds up across all 4 variants (0.9688–0.9728 AUROC, pristine through social_roundtrip)

**Before closing the session:**
- [ ] Checkpoint persisted — committed (Option A) or pushed to Kaggle Dataset (Option B, Cell 9)
- [ ] `l1_clip_head.pt` downloaded and wired into backend via `L1_MODEL_PATH` in `backend/.env`
