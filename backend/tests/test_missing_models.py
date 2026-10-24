"""Exercise missing-model code paths without downloading PyTorch or model weights."""
import ast
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def function_from_source(filename, name, class_name=None):
    module = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    nodes = module.body
    if class_name:
        nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == class_name).body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    return compile(ast.Module(body=[node], type_ignores=[]), filename, "exec")

def test_missing_video_checkpoint_never_initializes_random_model(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_MODEL_PATH", str(tmp_path / "missing.pth"))
    namespace = {"os": os, "__file__": str(ROOT / "video_inference.py"), "_model": None}
    exec(function_from_source("video_inference.py", "get_model"), namespace)
    with pytest.raises(RuntimeError, match="checkpoint missing"):
        namespace["get_model"]()
    assert namespace["_model"] is None

def test_audio_unavailable_never_returns_mock_verdict():
    namespace = {}
    exec(function_from_source("audio_detector.py", "analyze_audio", "AudioDeepfakeDetector"), namespace)
    class Unavailable:
        _model_loaded = False
    with pytest.raises(RuntimeError, match="no prediction"):
        namespace["analyze_audio"](Unavailable(), "anything.wav")
