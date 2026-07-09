import io
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.trufor import _resolve_python_executable, _resolve_trufor_layout, run_trufor_inference


def make_png(size=(64, 64), color=(100, 140, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def build_trufor_checkout(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "TruFor"
    workdir = repo_root / "TruFor_train_test"
    (workdir / "lib" / "config").mkdir(parents=True, exist_ok=True)
    (workdir / "pretrained_models" / "segformers").mkdir(parents=True, exist_ok=True)
    (workdir / "pretrained_models" / "noiseprint++").mkdir(parents=True, exist_ok=True)
    (workdir / "lib" / "config" / "trufor_ph3.yaml").write_text("MODEL: {}\n", encoding="utf-8")
    (workdir / "pretrained_models" / "segformers" / "mit_b2.pth").write_bytes(b"segformer")
    (workdir / "pretrained_models" / "noiseprint++" / "noiseprint++_test.pth").write_bytes(
        b"noiseprint"
    )
    (workdir / "trufor_conda.yaml").write_text("name: trufor\n", encoding="utf-8")
    (workdir / "test.py").write_text("print('stub')\n", encoding="utf-8")
    model_file = tmp_path / "trufor.pth.tar"
    model_file.write_bytes(b"weights")
    return repo_root, model_file


def fake_settings(repo_root: Path, model_file: Path, python_executable: str = "python"):
    return SimpleNamespace(
        l2_trufor_repo_dir=str(repo_root),
        l2_trufor_model_file=str(model_file),
        l2_trufor_python_executable=python_executable,
        l2_trufor_device="-1",
        l2_trufor_experiment="trufor_ph3",
        l2_trufor_timeout_seconds=30.0,
    )


def test_resolve_trufor_layout_accepts_official_checkout_shape(tmp_path):
    repo_root, model_file = build_trufor_checkout(tmp_path)

    layout = _resolve_trufor_layout(str(repo_root), str(model_file), "trufor_ph3")

    assert layout.repo_root == repo_root.resolve()
    assert layout.workdir == (repo_root / "TruFor_train_test").resolve()
    assert layout.entrypoint.name == "test.py"
    assert layout.config_file.name == "trufor_ph3.yaml"
    assert layout.segformer_weights.name == "mit_b2.pth"
    assert "noiseprint++" in str(layout.noiseprint_weights)


def test_run_trufor_inference_parses_official_npz_output(monkeypatch, tmp_path):
    repo_root, model_file = build_trufor_checkout(tmp_path)
    monkeypatch.setattr(
        "app.trufor.get_settings",
        lambda: fake_settings(repo_root=repo_root, model_file=model_file),
    )
    monkeypatch.setattr("app.trufor._resolve_python_executable", lambda executable: "python")

    def fake_run(command, cwd, capture_output, text, encoding, errors, timeout, check):
        output_dir = Path(command[5])
        output_dir.mkdir(parents=True, exist_ok=True)
        np.savez(
            output_dir / "claim-input.png.npz",
            map=np.array([[0.1, 0.8], [0.2, 0.9]], dtype=np.float32),
            conf=np.array([[0.7, 0.9], [0.6, 0.8]], dtype=np.float32),
            score=np.array(0.83, dtype=np.float32),
            imgsize=np.array([64, 64], dtype=np.int32),
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.trufor.subprocess.run", fake_run)

    result = run_trufor_inference(make_png())

    assert result.score == pytest.approx(0.83, abs=1e-4)
    assert result.confidence == pytest.approx(0.749, abs=2e-3)
    assert result.heatmap_png.startswith(b"\x89PNG")
    assert result.heatmap_mean > 0
    assert result.heatmap_max > 0
    assert result.confidence_mean == pytest.approx(0.749, abs=2e-3)
    assert result.model_version == "trufor:trufor.pth.tar"


def test_run_trufor_inference_reports_missing_runtime_dependency(monkeypatch, tmp_path):
    repo_root, model_file = build_trufor_checkout(tmp_path)
    monkeypatch.setattr(
        "app.trufor.get_settings",
        lambda: fake_settings(repo_root=repo_root, model_file=model_file, python_executable="python"),
    )
    monkeypatch.setattr("app.trufor._resolve_python_executable", lambda executable: "python")

    def fake_run(command, cwd, capture_output, text, encoding, errors, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                "ModuleNotFoundError: No module named 'yacs'\n"
            ),
        )

    monkeypatch.setattr("app.trufor.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        run_trufor_inference(make_png())

    message = str(exc_info.value)
    assert "TruFor runtime dependency 'yacs' is missing" in message
    assert "trufor_conda.yaml" in message


def test_resolve_python_executable_rejects_missing_path(tmp_path):
    with pytest.raises(RuntimeError) as exc_info:
        _resolve_python_executable(str(tmp_path / "missing-python.exe"))

    assert "TruFor Python executable does not exist" in str(exc_info.value)


def test_run_trufor_inference_reports_timeout(monkeypatch, tmp_path):
    repo_root, model_file = build_trufor_checkout(tmp_path)
    monkeypatch.setattr(
        "app.trufor.get_settings",
        lambda: fake_settings(repo_root=repo_root, model_file=model_file),
    )
    monkeypatch.setattr("app.trufor._resolve_python_executable", lambda executable: "python")

    def fake_run(command, cwd, capture_output, text, encoding, errors, timeout, check):
        raise subprocess.TimeoutExpired(cmd=command, timeout=timeout)

    monkeypatch.setattr("app.trufor.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        run_trufor_inference(make_png())

    assert "timed out after 30s" in str(exc_info.value)


def test_run_trufor_inference_reports_missing_required_output_keys(monkeypatch, tmp_path):
    repo_root, model_file = build_trufor_checkout(tmp_path)
    monkeypatch.setattr(
        "app.trufor.get_settings",
        lambda: fake_settings(repo_root=repo_root, model_file=model_file),
    )
    monkeypatch.setattr("app.trufor._resolve_python_executable", lambda executable: "python")

    def fake_run(command, cwd, capture_output, text, encoding, errors, timeout, check):
        output_dir = Path(command[5])
        output_dir.mkdir(parents=True, exist_ok=True)
        np.savez(
            output_dir / "claim-input.png.npz",
            conf=np.array([[0.7, 0.9], [0.6, 0.8]], dtype=np.float32),
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.trufor.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        run_trufor_inference(make_png())

    assert "missing required keys: map, score" in str(exc_info.value)
