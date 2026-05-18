import subprocess
import tempfile
from pathlib import Path

import pytest

from common import czi_pyramidizer


def test_check_needs_pyramid_builds_expected_command(monkeypatch):
    recorded = {}

    def fake_run(command, stdout, stderr, check, text, timeout):
        recorded["command"] = tuple(command)
        recorded["timeout"] = timeout
        stdout.write("needed")
        stderr.write("")
        return subprocess.CompletedProcess(command, 10)

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
    def fake_run(command, stdout, stderr, check, text, timeout):
        stdout.write("")
        stderr.write("boom")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    with pytest.raises(czi_pyramidizer.CziPyramidizerError) as excinfo:
        czi_pyramidizer.check_needs_pyramid("input.czi", timeout_sec=5)

    assert excinfo.value.run_result is not None
    assert excinfo.value.run_result.exit_code == 1


def test_build_pyramid_returns_no_action(monkeypatch):
    recorded = {}

    def fake_run(command, stdout, stderr, check, text, timeout):
        recorded["command"] = tuple(command)
        stdout.write("skipped")
        stderr.write("")
        return subprocess.CompletedProcess(command, 11)

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


def test_read_tail_reads_only_tail_and_replaces_decode_errors():
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log_file:
        log_file.buffer.write(b"123456789\xffEND")

        result = czi_pyramidizer._read_tail(log_file, 4)

    assert result == "�END"


def test_run_timeout_keeps_only_stdout_stderr_tail(monkeypatch):
    def fake_run(command, stdout, stderr, check, text, timeout):
        stdout.write("a" * (czi_pyramidizer.MAX_LOG_TAIL_CHARS + 100))
        stderr.write("b" * (czi_pyramidizer.MAX_LOG_TAIL_CHARS + 100))
        stdout.flush()
        stderr.flush()
        raise subprocess.TimeoutExpired(command, timeout, output="fallback-stdout", stderr="fallback-stderr")

    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    with pytest.raises(czi_pyramidizer.CziPyramidizerError) as excinfo:
        czi_pyramidizer._run(("mock-pyramidizer", "--check-only"), timeout_sec=2)

    run_result = excinfo.value.run_result
    assert run_result is not None
    assert run_result.exit_code == czi_pyramidizer.GENERAL_FAILURE_EXIT_CODE
    assert len(run_result.stdout) == czi_pyramidizer.MAX_LOG_TAIL_CHARS
    assert len(run_result.stderr) == czi_pyramidizer.MAX_LOG_TAIL_CHARS
    assert run_result.stdout == "a" * czi_pyramidizer.MAX_LOG_TAIL_CHARS
    assert run_result.stderr == "b" * czi_pyramidizer.MAX_LOG_TAIL_CHARS


def test_run_timeout_falls_back_to_exception_output_when_logs_are_empty(monkeypatch):
    def fake_run(command, stdout, stderr, check, text, timeout):
        raise subprocess.TimeoutExpired(command, timeout, output=b"out\xff", stderr=b"err\xff")

    monkeypatch.setattr(czi_pyramidizer.subprocess, "run", fake_run)

    with pytest.raises(czi_pyramidizer.CziPyramidizerError) as excinfo:
        czi_pyramidizer._run(("mock-pyramidizer", "--check-only"), timeout_sec=2)

    run_result = excinfo.value.run_result
    assert run_result is not None
    assert run_result.stdout == "out�"
    assert run_result.stderr == "err�"
