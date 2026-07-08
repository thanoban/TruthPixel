import io
import subprocess

import pytest
from PIL import Image

from app.analyzers.l4_metadata import MetadataAnalyzer
from app.schemas import ClaimContext


def make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (140, 120, 90)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_metadata_analyzer_handles_missing_c2patool(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("c2patool")

    monkeypatch.setattr("app.analyzers.l4_metadata.subprocess.run", fake_run)

    result = await MetadataAnalyzer().analyze(make_jpeg(), ClaimContext())

    assert result.error is None
    assert result.evidence["c2pa"]["status"] == "unavailable"
    assert result.evidence["c2pa"]["checked"] is False
    assert result.evidence["c2pa"]["tool_available"] is False


@pytest.mark.asyncio
async def test_metadata_analyzer_surfaces_c2pa_manifest_details(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "--info" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                "Information for asset.jpg\nManifest store size = 1234\nValidated\nOne manifest\n",
                "",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            (
                '{"active_manifest":"manifest-1",'
                '"manifests":[{"label":"manifest-1"}],'
                '"validation_status":[{"code":"signingCredential.untrusted"}]}'
            ),
            "",
        )

    monkeypatch.setattr("app.analyzers.l4_metadata.subprocess.run", fake_run)

    result = await MetadataAnalyzer().analyze(make_jpeg(), ClaimContext())

    assert result.error is None
    assert len(calls) == 2
    assert result.evidence["c2pa"]["status"] == "manifest_present"
    assert result.evidence["c2pa"]["manifest_count"] == 1
    assert result.evidence["c2pa"]["active_manifest"] == "manifest-1"
    assert result.evidence["c2pa"]["validation_status"] == ["signingCredential.untrusted"]
