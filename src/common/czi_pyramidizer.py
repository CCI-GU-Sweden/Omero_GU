from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from common import conf


SUCCESS_EXIT_CODE = 0
GENERAL_FAILURE_EXIT_CODE = 1
PYRAMID_NEEDED_EXIT_CODE = 10
NO_ACTION_EXIT_CODE = 11
ARGUMENT_ERROR_EXIT_CODE = 99


@dataclass(frozen=True)
class CziPyramidizerRunResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code in {SUCCESS_EXIT_CODE, NO_ACTION_EXIT_CODE, PYRAMID_NEEDED_EXIT_CODE}


@dataclass(frozen=True)
class CziPyramidCheckResult:
    needs_pyramid: bool
    run_result: CziPyramidizerRunResult


@dataclass(frozen=True)
class CziPyramidBuildResult:
    created_output: bool
    run_result: CziPyramidizerRunResult


class CziPyramidizerError(RuntimeError):
    def __init__(self, message: str, run_result: CziPyramidizerRunResult | None = None):
        super().__init__(message)
        self.run_result = run_result


def get_version(timeout_sec: int | None = None) -> CziPyramidizerRunResult:
    command = (conf.CZI_PYRAMIDIZER_BIN, "--version")
    return _run(command, timeout_sec=timeout_sec)


def check_needs_pyramid(path: str | Path, timeout_sec: int | None = None) -> CziPyramidCheckResult:
    source_path = str(path)
    command = _build_check_command(source_path)
    run_result = _run(command, timeout_sec=timeout_sec)

    if run_result.exit_code == SUCCESS_EXIT_CODE:
        return CziPyramidCheckResult(needs_pyramid=False, run_result=run_result)

    if run_result.exit_code == PYRAMID_NEEDED_EXIT_CODE:
        return CziPyramidCheckResult(needs_pyramid=True, run_result=run_result)

    raise CziPyramidizerError(
        f"czi-pyramidizer check failed for {source_path} with exit code {run_result.exit_code}",
        run_result=run_result,
    )


def build_pyramid(source_path: str | Path, destination_path: str | Path, timeout_sec: int | None = None) -> CziPyramidBuildResult:
    source = str(source_path)
    destination = str(destination_path)
    command = _build_pyramid_command(source, destination)
    run_result = _run(command, timeout_sec=timeout_sec)

    if run_result.exit_code == SUCCESS_EXIT_CODE:
        return CziPyramidBuildResult(created_output=True, run_result=run_result)

    if run_result.exit_code == NO_ACTION_EXIT_CODE:
        return CziPyramidBuildResult(created_output=False, run_result=run_result)

    raise CziPyramidizerError(
        f"czi-pyramidizer build failed for {source} with exit code {run_result.exit_code}",
        run_result=run_result,
    )


def _build_check_command(source_path: str) -> tuple[str, ...]:
    return (
        conf.CZI_PYRAMIDIZER_BIN,
        "-s",
        source_path,
        "-p",
        str(conf.CZI_PYRAMIDIZER_THRESHOLD),
        "--check-only",
    )


def _build_pyramid_command(source_path: str, destination_path: str) -> tuple[str, ...]:
    return (
        conf.CZI_PYRAMIDIZER_BIN,
        "-s",
        source_path,
        "-d",
        destination_path,
        "-n",
        str(conf.CZI_PYRAMIDIZER_MODE),
        "-t",
        str(conf.CZI_PYRAMIDIZER_TILE_SIZE),
        "-m",
        str(conf.CZI_PYRAMIDIZER_MAX_TOP_LEVEL),
        "-p",
        str(conf.CZI_PYRAMIDIZER_THRESHOLD),
        "-o",
    )


def _run(command: Sequence[str], timeout_sec: int | None = None) -> CziPyramidizerRunResult:
    effective_timeout = conf.CZI_PYRAMIDIZER_TIMEOUT_SEC if timeout_sec is None else timeout_sec

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=effective_timeout,
        )
    except FileNotFoundError as exc:
        raise CziPyramidizerError(f"Unable to find czi-pyramidizer binary: {conf.CZI_PYRAMIDIZER_BIN}") from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode() if exc.stdout else "")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode() if exc.stderr else "")
        run_result = CziPyramidizerRunResult(tuple(command), GENERAL_FAILURE_EXIT_CODE, stdout, stderr)
        raise CziPyramidizerError(
            f"czi-pyramidizer timed out after {effective_timeout} seconds",
            run_result=run_result,
        ) from exc

    return CziPyramidizerRunResult(
        command=tuple(str(arg) for arg in command),
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def default_pyramidized_path(source_path: str | Path) -> str:
    source = Path(source_path)
    return os.fspath(source.with_suffix(".pyramidized.czi"))