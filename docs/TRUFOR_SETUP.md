# TruFor Setup

This is the exact runtime contract TruthPixel expects for the real `L2` TruFor module.

## What Was Validated

- Upstream checkout shape validated against the official `grip-unina/TruFor` repository at commit `ae54475`.
- Upstream inference entrypoint validated against `TruFor_train_test/test.py`.
- Upstream weight archive validated against the published MD5 from the official README:
  - file: `TruFor_weights.zip`
  - expected MD5: `7bee48f3476c75616c3c5721ab256ff8`
  - verified MD5 here: `7bee48f3476c75616c3c5721ab256ff8`
- Official runtime contract confirmed from the upstream docs:
  - command shape: `python test.py -in <image> -out <output_dir> -exp trufor_ph3 TEST.MODEL_FILE "<path-to-trufor.pth.tar>"`
  - output `.npz` keys: `map`, `conf`, `score`, `imgsize`

## Required Files

TruthPixel accepts either:

- `L2_TRUFOR_REPO_DIR=<path-to-TruFor-repo-root>`
- or `L2_TRUFOR_REPO_DIR=<path-containing-TruFor_train_test>`

Inside that checkout, the following must exist:

- `TruFor_train_test/test.py`
- `TruFor_train_test/lib/config/trufor_ph3.yaml`
- `TruFor_train_test/pretrained_models/segformers/mit_b2.pth`
- at least one file under `TruFor_train_test/pretrained_models/noiseprint++/`

The final checkpoint is separate and must exist at `L2_TRUFOR_MODEL_FILE`.

The official published archive unpacks the final checkpoint as:

- `weights/trufor.pth.tar`

## TruthPixel Environment Variables

Set these for the backend:

```powershell
$env:L2_TRUFOR_REPO_DIR="D:\path\to\TruFor"
$env:L2_TRUFOR_MODEL_FILE="D:\path\to\TruFor_weights\weights\trufor.pth.tar"
$env:L2_TRUFOR_PYTHON_EXECUTABLE="D:\path\to\python.exe"
$env:L2_TRUFOR_DEVICE="-1"
$env:L2_TRUFOR_EXPERIMENT="trufor_ph3"
$env:L2_TRUFOR_TIMEOUT_SECONDS="180"
```

Notes:

- `L2_TRUFOR_PYTHON_EXECUTABLE` should point to a dedicated TruFor-capable environment, not the general backend interpreter.
- `L2_TRUFOR_DEVICE=-1` forces CPU mode.
- `L2_TRUFOR_DEVICE=0` uses GPU `0` if the TruFor environment supports CUDA.

## Upstream Runtime Requirements

The official upstream environment is defined in:

- `TruFor_train_test/trufor_conda.yaml`

Important runtime characteristics from that file:

- Python `3.7`
- PyTorch `1.11.0`
- torchvision `0.12.0`
- `yacs`
- `pyyaml`
- `timm`
- `mmcv-full`
- `mmsegmentation`
- `jpegio`
- `opencv-python`

TruthPixel does not import these packages directly. They only need to exist in the Python environment pointed to by `L2_TRUFOR_PYTHON_EXECUTABLE`.

## Smoke Validation Result On This Machine

Real local smoke command used against the official `test.py` and the verified official checkpoint:

```powershell
python test.py -g -1 `
  -in D:\PROJECTS\Startup\TruthPixel\.codex\tmp\trufor-smoke.png `
  -out D:\PROJECTS\Startup\TruthPixel\.codex\tmp\trufor-out `
  -exp trufor_ph3 `
  TEST.MODEL_FILE D:\PROJECTS\Startup\TruthPixel\.codex\tmp\TruFor-assets\weights\weights\trufor.pth.tar
```

Observed result with the current host Python:

- the official entrypoint started correctly
- repo layout and checkpoint path were accepted
- runtime then failed on a missing upstream dependency: `ModuleNotFoundError: No module named 'yacs'`

That is why TruthPixel now surfaces a targeted preflight/runtime error telling you to use the upstream TruFor environment or point `L2_TRUFOR_PYTHON_EXECUTABLE` at a compatible interpreter.

## What TruthPixel Persists

When TruFor succeeds, TruthPixel:

- stores the anomaly heatmap as a PNG artifact
- links it back into the L2 signal evidence as `heatmap_download_path`
- keeps the original upload and heatmap together in claim artifacts

The backend tests cover:

- direct L2 heatmap persistence
- synchronous claim artifact persistence
- async claim artifact persistence
