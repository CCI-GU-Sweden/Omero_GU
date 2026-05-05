import subprocess
from pathlib import Path

import pytest

from common import czi_pyramidizer


def test_check_needs_pyramid_builds_expected_command(monkeypatch):
    recorded = {}

    def fake_run(command, capture_output, check, text, timeout):
        recorded["command"] = tuple(command)
        recorded["timeout"] = timeout
        return subprocess.CompletedProcess(command, 10, "needed", "")

    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_BIN", "mock-pyramidizer")
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_THRESHOLD", 2048)
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_TIMEOUT_SEC", 123)
    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    result = czi_pyramidizer.check_needs_pyramid("input.czi")

    assert result.needs_pyramid is True
    assert recorded["timeout"] == 123
    assert recorded["command"] == (
        "mock-pyramidizer",
        "-s",
        "input.czi",
        "-p",
        "2048",
        "--check-only",
    )


def test_check_needs_pyramid_raises_on_generic_failure(monkeypatch):
    def fake_run(command, capture_output, check, text, timeout):
        return subprocess.CompletedProcess(command, 1, "", "boom")

    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    with pytest.raises(czi_pyramidizer.CziPyramidizerError) as excinfo:
        czi_pyramidizer.check_needs_pyramid("input.czi", timeout_sec=5)

    assert excinfo.value.run_result is not None
    assert excinfo.value.run_result.exit_code == 1


def test_build_pyramid_returns_no_action(monkeypatch):
    recorded = {}

    def fake_run(command, capture_output, check, text, timeout):
        recorded["command"] = tuple(command)
        return subprocess.CompletedProcess(command, 11, "skipped", "")

    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_BIN", "mock-pyramidizer")
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_MODE", "IfNeeded")
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_TILE_SIZE", 512)
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_MAX_TOP_LEVEL", 256)
    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_THRESHOLD", 1024)
    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    result = czi_pyramidizer.build_pyramid("input.czi", "output.czi", timeout_sec=7)

    assert result.created_output is False
    assert recorded["command"] == (
        "mock-pyramidizer",
        "-s",
        "input.czi",
        "-d",
        "output.czi",
        "-n",
        "IfNeeded",
        "-t",
        "512",
        "-m",
        "256",
        "-p",
        "1024",
        "-o",
    )


def test_default_pyramidized_path_uses_distinct_czi_name():
    assert Path(czi_pyramidizer.default_pyramidized_path("folder/sample.czi")) == Path("folder/sample.pyramidized.czi")