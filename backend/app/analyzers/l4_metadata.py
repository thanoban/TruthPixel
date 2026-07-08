import io
import json
import os
import re
import subprocess
import tempfile
from typing import Any

from PIL import ExifTags, Image

from ..config import get_settings
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer

EDITING_SOFTWARE_MARKERS = ("photoshop", "gimp", "lightroom", "snapseed", "canva", "pixlr")
MANIFEST_COUNT_RE = re.compile(r"\b(?:(?P<one>one)|(?P<count>\d+))\s+manifest(?:s)?\b", re.I)


def _image_suffix(image: Image.Image) -> str:
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "HEIF": ".heic",
        "HEIC": ".heic",
    }.get((image.format or "").upper(), ".img")


def _combine_output(stdout: str, stderr: str) -> str:
    text = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    return text.strip()


def _extract_manifest_count(summary: str) -> int | None:
    lower = summary.lower()
    if "no manifests" in lower or "no manifest" in lower:
        return 0
    match = MANIFEST_COUNT_RE.search(summary)
    if not match:
        return None
    if match.group("one"):
        return 1
    return int(match.group("count"))


def _classify_c2pa_status(summary: str, manifest_count: int | None, returncode: int) -> str:
    lower = summary.lower()
    if manifest_count is not None:
        return "manifest_present" if manifest_count > 0 else "manifest_absent"
    if "no c2pa" in lower or "manifest store size = 0" in lower:
        return "manifest_absent"
    if returncode == 0:
        return "checked"
    return "error"


def _find_first_key(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = _find_first_key(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_first_key(value, key)
            if found is not None:
                return found
    return None


def _collect_validation_status(payload: Any) -> list[str]:
    entries: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "validation_status":
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            entry = item.get("code") or item.get("explanation") or json.dumps(
                                item, sort_keys=True
                            )
                            entries.append(str(entry))
                        else:
                            entries.append(str(item))
                elif value:
                    entries.append(str(value))
            else:
                entries.extend(_collect_validation_status(value))
    elif isinstance(payload, list):
        for value in payload:
            entries.extend(_collect_validation_status(value))
    return entries


def _manifest_count_from_payload(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    manifests = payload.get("manifests")
    if isinstance(manifests, list):
        return len(manifests)
    if isinstance(manifests, dict):
        return len(manifests)
    return None


def _trust_args() -> list[str]:
    settings = get_settings()
    args: list[str] = []
    if settings.c2patool_trust_anchors:
        args.extend(["--trust_anchors", settings.c2patool_trust_anchors])
    if settings.c2patool_allowed_list:
        args.extend(["--allowed_list", settings.c2patool_allowed_list])
    if settings.c2patool_trust_config:
        args.extend(["--trust_config", settings.c2patool_trust_config])
    return args


def _run_c2patool(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=get_settings().c2patool_timeout_seconds,
        check=False,
    )


def _inspect_c2pa(image: bytes, suffix: str) -> dict[str, Any]:
    tool_path = get_settings().c2patool_path
    fd, asset_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(asset_path, "wb") as handle:
            handle.write(image)

        try:
            info = _run_c2patool([tool_path, asset_path, "--info"])
        except FileNotFoundError:
            return {
                "checked": False,
                "tool_available": False,
                "status": "unavailable",
                "summary": "c2patool executable not found",
                "manifest_count": None,
                "active_manifest": None,
                "validation_status": [],
            }
        except subprocess.TimeoutExpired:
            return {
                "checked": False,
                "tool_available": True,
                "status": "timeout",
                "summary": "c2patool timed out while reading the asset",
                "manifest_count": None,
                "active_manifest": None,
                "validation_status": [],
            }

        summary = _combine_output(info.stdout, info.stderr)
        manifest_count = _extract_manifest_count(summary)
        status = _classify_c2pa_status(summary, manifest_count, info.returncode)
        result: dict[str, Any] = {
            "checked": True,
            "tool_available": True,
            "status": status,
            "summary": summary,
            "manifest_count": manifest_count,
            "active_manifest": None,
            "validation_status": [],
        }
        if status != "manifest_present":
            return result

        json_command = [tool_path, asset_path]
        trust_args = _trust_args()
        if trust_args:
            json_command.extend(["trust", *trust_args])

        try:
            manifest = _run_c2patool(json_command)
        except subprocess.TimeoutExpired:
            result["status"] = "manifest_present"
            result["summary"] = (summary + "\nC2PA manifest detail lookup timed out.").strip()
            return result

        if manifest.returncode != 0:
            detail_error = _combine_output(manifest.stdout, manifest.stderr)
            if detail_error:
                result["summary"] = f"{summary}\n{detail_error}".strip()
            return result

        try:
            payload = json.loads(manifest.stdout)
        except json.JSONDecodeError:
            detail_error = manifest.stdout.strip()
            if detail_error:
                result["summary"] = f"{summary}\n{detail_error}".strip()
            return result

        payload_manifest_count = _manifest_count_from_payload(payload)
        if payload_manifest_count is not None:
            result["manifest_count"] = payload_manifest_count
        result["active_manifest"] = _find_first_key(payload, "active_manifest")
        result["validation_status"] = _collect_validation_status(payload)
        return result
    finally:
        try:
            os.remove(asset_path)
        except OSError:
            pass


class MetadataAnalyzer(Analyzer):
    """L4 — metadata & provenance (EXIF now; c2patool / SynthID checks later).

    IMPORTANT WEIGHTING RULE: absent/clean metadata is NEUTRAL evidence, never proof —
    a genuine phone photo re-saved via WhatsApp loses EXIF too, and a screenshot wipes it.
    Only *positive* traces (editing-software tags) move the score meaningfully.
    The combination "metadata absent + other layers flagged" is scored by fusion, not here.
    """

    layer = Layer.L4_METADATA

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        img = Image.open(io.BytesIO(image))
        exif = img.getexif()
        tags = {ExifTags.TAGS.get(k, str(k)): str(v) for k, v in exif.items()}

        software = tags.get("Software", "").lower()
        editing_trace = any(m in software for m in EDITING_SOFTWARE_MARKERS)
        has_camera_info = bool(tags.get("Make") or tags.get("Model"))

        if editing_trace:
            score, confidence = 0.75, 0.6
        elif has_camera_info:
            score, confidence = 0.35, 0.3
        else:
            # Metadata absent — neutral by design (see docstring).
            score, confidence = 0.5, 0.15

        c2pa = _inspect_c2pa(image, _image_suffix(img))

        return SignalResult(
            layer=self.layer,
            score=score,
            confidence=confidence,
            evidence={
                "exif_present": bool(tags),
                "camera": f"{tags.get('Make', '')} {tags.get('Model', '')}".strip(),
                "software": tags.get("Software", ""),
                "editing_software_trace": editing_trace,
                "datetime": tags.get("DateTime", ""),
                # Provenance data is surfaced for reviewers now; score weighting stays conservative
                # until we define trust policy and manifest semantic parsing.
                "c2pa": c2pa,
            },
        )
