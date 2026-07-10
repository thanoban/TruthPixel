"""TruthPixel demo harness — submits curated claim images to a live backend and prints
the fused report for each, in plain English.

This is the tool behind ROADMAP.md's Phase 0 exit criterion ("the screenshot-of-AI-image
demo case is flagged with a correct explanation") and USE_CASES.md's demo script item.

Five cases, by design intent:
  1. real_damage       — a genuine "this is what a real claim looks like" baseline
  2. ai_fake           — a fully AI-generated image (tests L1)
  3. inpainted         — a real photo with a manipulated/inpainted region (tests L2)
  4. screenshot_of_ai  — (2) or (1) run through the same screenshot-simulation pipeline
                          used in ml/layer1_aigen/augment.py (tests L3 + the
                          screenshot-evasion combo rule — this is the actual exit
                          criterion case)
  5. reused_photo      — (1) submitted twice under different orders (tests L5's
                          intra-system reuse detection)

Only (4) and (5) can be produced honestly without an external image source — a "fake AI
image" and a "manipulated image" both require either a real generative model or real
manipulation tooling, neither of which this script fabricates procedurally (see
docs/COLAB_TRAINING.md / docs/ML_PLAN.md for why: a solid-color square with noise is not
a meaningful stand-in for what SDXL/GAN artifacts actually look like, and claiming
otherwise would misrepresent what got tested). Supply --real-damage / --ai-fake
/ --inpainted with real image paths for the full five-case demo; omitted cases are
skipped with a note on where to source one.

Usage:
    backend/.venv/Scripts/python scripts/demo.py \\
        --real-damage path/to/real.jpg \\
        --ai-fake path/to/fake.jpg \\
        --inpainted path/to/inpainted.jpg

    # Or just the two reproducible cases, no external images needed:
    backend/.venv/Scripts/python scripts/demo.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from PIL import Image

from ml.layer1_aigen.augment import build_robustness_variants

DEFAULT_API_URL = "http://localhost:8000"


def _placeholder_image() -> bytes:
    """A clearly-labeled stand-in product photo, used only when no --real-damage image is
    supplied, so the reused-photo and screenshot-sim cases still run out of the box. This
    is NOT presented as a real damage photo anywhere in the output.
    """
    img = Image.new("RGB", (512, 512), color=(150, 120, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _load_image_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def _pil_to_jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def submit_claim(
    *,
    api_url: str,
    api_key: str | None,
    image_bytes: bytes,
    filename: str,
    order_id: str,
    product_sku: str = "DEMO-SKU",
    claim_reason: str = "item arrived damaged",
) -> dict:
    headers = {"X-API-Key": api_key} if api_key else {}
    files = {"image": (filename, image_bytes, "image/jpeg")}
    data = {"order_id": order_id, "product_sku": product_sku, "claim_reason": claim_reason}
    response = httpx.post(
        f"{api_url}/v1/claims", headers=headers, files=files, data=data, timeout=120.0
    )
    response.raise_for_status()
    return response.json()


def render_report(label: str, claim: dict) -> None:
    fusion = claim["fusion"]
    print(f"\n{'=' * 72}")
    print(f"CASE: {label}")
    print(f"{'=' * 72}")
    print(f"claim_id: {claim['claim_id']}")
    print(
        f"risk_score: {fusion['risk_score']:.2f}  "
        f"needs_review: {fusion['needs_review']}  "
        f"fusion_version: {fusion['fusion_version']}"
    )
    print("\nsignals:")
    for signal in claim["signals"]:
        score = "n/a" if signal["score"] is None else f"{signal['score']:.2f}"
        confidence = f"{signal['confidence']:.2f}"
        contribution = fusion["contributions"].get(signal["layer"])
        contribution_str = "n/a" if contribution is None else f"{contribution:.2f}"
        status = f"ERROR: {signal['error']}" if signal["error"] else "ok"
        print(
            f"  {signal['layer']:<14} score={score:<5} confidence={confidence:<5} "
            f"contribution={contribution_str:<5} [{status}]"
        )
        note = signal.get("evidence", {}).get("note")
        if note:
            print(f"    note: {note}")

    if claim["agent_findings"]:
        print("\nagent findings:")
        for finding in claim["agent_findings"]:
            score = "n/a" if finding["score"] is None else f"{finding['score']:.2f}"
            print(f"  {finding['agent']}: score={score}")
            for item in finding["findings"]:
                print(f"    - {item}")

    print(f"\nreport: {claim['report_text']}")


def main() -> int:
    # Windows consoles often default stdout to a legacy codepage (cp1252/cp437), which
    # mangles the em-dashes/section signs in this script's own output (found via a real
    # run: "—" and "§" printed as "�"). Force UTF-8 so output is readable regardless of
    # which terminal (PowerShell, cmd, Git Bash) this runs in.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=None, help="X-API-Key, only needed if API_AUTH_ENABLED=true")
    parser.add_argument("--real-damage", default=None, help="path to a genuine damage claim photo")
    parser.add_argument("--ai-fake", default=None, help="path to a fully AI-generated image")
    parser.add_argument("--inpainted", default=None, help="path to a manipulated/inpainted photo")
    args = parser.parse_args()

    try:
        health = httpx.get(f"{args.api_url}/health", timeout=10.0)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Backend not reachable at {args.api_url}: {exc}", file=sys.stderr)
        print("Start it first: cd backend && uvicorn app.main:app --port 8000", file=sys.stderr)
        return 1
    print(f"Backend healthy: {health.json()}")

    real_damage_bytes = (
        _load_image_bytes(args.real_damage) if args.real_damage else _placeholder_image()
    )
    if not args.real_damage:
        print(
            "\n[note] No --real-damage supplied — using a plain placeholder image so the "
            "reused-photo and screenshot cases still run. This is NOT a real damage photo."
        )

    cases_run = 0

    # Case 1: real damage baseline (or placeholder)
    report = submit_claim(
        api_url=args.api_url,
        api_key=args.api_key,
        image_bytes=real_damage_bytes,
        filename="real_damage.jpg",
        order_id="DEMO-1-REAL",
    )
    render_report(
        "real_damage" + (" (placeholder — supply --real-damage for a real one)" if not args.real_damage else ""),
        report,
    )
    cases_run += 1

    # Case 2: AI fake
    if args.ai_fake:
        report = submit_claim(
            api_url=args.api_url,
            api_key=args.api_key,
            image_bytes=_load_image_bytes(args.ai_fake),
            filename="ai_fake.jpg",
            order_id="DEMO-2-AIFAKE",
        )
        render_report("ai_fake", report)
        cases_run += 1
    else:
        print(
            "\n[skipped] ai_fake — supply --ai-fake path/to/image.jpg. Source one from "
            "GenImage/CIFAKE (see docs/ML_PLAN.md) or generate one with any SDXL demo."
        )

    # Case 3: inpainted / manipulated
    if args.inpainted:
        report = submit_claim(
            api_url=args.api_url,
            api_key=args.api_key,
            image_bytes=_load_image_bytes(args.inpainted),
            filename="inpainted.jpg",
            order_id="DEMO-3-INPAINT",
        )
        render_report("inpainted", report)
        cases_run += 1
    else:
        print(
            "\n[skipped] inpainted — supply --inpainted path/to/image.jpg. Source one from "
            "CASIA v2 (see docs/COMPETITORS.md §8) or make one with GIMP/Photoshop "
            "content-aware fill on a small region of a real photo."
        )

    # Case 4: screenshot-of-AI — the actual Phase 0 exit criterion. Prefer the AI-fake
    # image if supplied (that's the real evasion scenario); fall back to the real-damage
    # image otherwise so this reproducible case always runs.
    screenshot_source_bytes = (
        _load_image_bytes(args.ai_fake) if args.ai_fake else real_damage_bytes
    )
    screenshot_source_label = "ai_fake" if args.ai_fake else ("real_damage" if args.real_damage else "placeholder")
    source_image = Image.open(io.BytesIO(screenshot_source_bytes))
    variants = build_robustness_variants(source_image)
    report = submit_claim(
        api_url=args.api_url,
        api_key=args.api_key,
        image_bytes=_pil_to_jpeg_bytes(variants["screenshot_sim"]),
        filename="screenshot_of_ai.jpg",
        order_id="DEMO-4-SCREENSHOT",
    )
    render_report(f"screenshot_of_ai (source: {screenshot_source_label})", report)
    cases_run += 1

    # Case 5: reused photo — submit the same real-damage/placeholder bytes under a
    # second, unrelated order. L5 should flag it against the case 1 claim.
    report = submit_claim(
        api_url=args.api_url,
        api_key=args.api_key,
        image_bytes=real_damage_bytes,
        filename="reused_photo.jpg",
        order_id="DEMO-5-REUSED",
    )
    render_report("reused_photo (same bytes as case 1, different order)", report)
    cases_run += 1

    print(f"\n{'=' * 72}")
    print(f"Ran {cases_run}/5 cases. Full five-case demo needs --ai-fake and --inpainted.")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
