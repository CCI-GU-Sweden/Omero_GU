from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from common import conf
from common import logger


SUCCESS_EXIT_CODE = 0
GENERAL_FAILURE_EXIT_CODE = 1
PYRAMID_NEEDED_EXIT_CODE = 10
NO_ACTION_EXIT_CODE = 11
ARGUMENT_ERROR_EXIT_CODE = 99
MAX_LOG_TAIL_CHARS = 8000


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
    result = _run(command, timeout_sec=timeout_sec)
    logger.debug(f"[czi-pyramidizer] Checked version with command {command!r}: exit_code={result.exit_code}, stdout={result.stdout!r}, stderr={result.stderr!r}")
    return result


def check_needs_pyramid(path: str | Path, timeout_sec: int | None = None) -> CziPyramidCheckResult:
    source_path = str(path)
    command = _build_check_command(source_path)
    run_result = _run(command, timeout_sec=timeout_sec)

    if run_result.exit_code == SUCCESS_EXIT_CODE:
        logger.debug(f"[czi-pyramidizer] check for {source_path} indicates no pyramid needed (exit code {run_result.exit_code})")
        return CziPyramidCheckResult(needs_pyramid=False, run_result=run_result)

    if run_result.exit_code == PYRAMID_NEEDED_EXIT_CODE:
        logger.debug(f"[czi-pyramidizer] check for {source_path} indicates pyramid needed (exit code {run_result.exit_code})")
        return CziPyramidCheckResult(needs_pyramid=True, run_result=run_result)

    logger.error(
        f"[czi-pyramidizer] check for {source_path} failed with exit code {run_result.exit_code}\n"
        f"  stderr: {run_result.stderr!r}\n"
        f"  stdout: {run_result.stdout!r}"
    )
    raise CziPyramidizerError(
        f"[czi-pyramidizer] check failed for {source_path} with exit code {run_result.exit_code}",
        run_result=run_result,
    )


def build_pyramid(source_path: str | Path, destination_path: str | Path, timeout_sec: int | None = None) -> CziPyramidBuildResult:
    source = str(source_path)
    destination = str(destination_path)
    command = _build_pyramid_command(source, destination)
    run_result = _run(command, timeout_sec=timeout_sec)

    if run_result.exit_code == SUCCESS_EXIT_CODE:
        logger.debug(f"[czi-pyramidizer] build for {source} succeeded (exit code {run_result.exit_code})")
        return CziPyramidBuildResult(created_output=True, run_result=run_result)

    if run_result.exit_code == NO_ACTION_EXIT_CODE:
        logger.warning(
            f"[czi-pyramidizer] build for {source} took no action (exit code {run_result.exit_code}) "
            f"despite check indicating pyramid was needed\n"
            f"  stderr: {run_result.stderr!r}\n"
            f"  stdout: {run_result.stdout!r}"
        )
        return CziPyramidBuildResult(created_output=False, run_result=run_result)

    logger.error(
        f"[czi-pyramidizer] build for {source} failed with exit code {run_result.exit_code}\n"
        f"  stderr: {run_result.stderr!r}\n"
        f"  stdout: {run_result.stdout!r}"
    )
    raise CziPyramidizerError(
        f"[czi-pyramidizer] build failed for {source} with exit code {run_result.exit_code}",
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
        # Keep subprocess output off RAM for large/verbose runs; only read a small tail for logs.
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file, tempfile.TemporaryFile(
            mode="w+t", encoding="utf-8"
        ) as stderr_file:
            try:
                completed = subprocess.run(
                    command,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    check=False,
                    text=True,
                    timeout=effective_timeout,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = _read_tail(stdout_file, MAX_LOG_TAIL_CHARS)
                stderr = _read_tail(stderr_file, MAX_LOG_TAIL_CHARS)
                if not stdout:
                    stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode(errors="replace") if exc.stdout else "")
                if not stderr:
                    stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode(errors="replace") if exc.stderr else "")

                run_result = CziPyramidizerRunResult(tuple(command), GENERAL_FAILURE_EXIT_CODE, stdout, stderr)
                raise CziPyramidizerError(
                    f"[czi-pyramidizer] czi-pyramidizer timed out after {effective_timeout} seconds",
                    run_result=run_result,
                ) from exc

            stdout = _read_tail(stdout_file, MAX_LOG_TAIL_CHARS)
            stderr = _read_tail(stderr_file, MAX_LOG_TAIL_CHARS)
    except FileNotFoundError as exc:
        raise CziPyramidizerError(f"[czi-pyramidizer] Unable to find czi-pyramidizer binary: {conf.CZI_PYRAMIDIZER_BIN}") from exc

    return CziPyramidizerRunResult(
        command=tuple(str(arg) for arg in command),
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def default_pyramidized_path(source_path: str | Path) -> str:
    source = Path(source_path)
    return os.fspath(source.with_suffix(".pyramidized.czi"))


def _read_tail(file_obj, max_chars: int) -> str:
    if max_chars <= 0:
        return ""

    # Use the underlying binary buffer to support end-relative seeks while
    # keeping text-mode file handles for subprocess/test compatibility.
    buffer_obj = getattr(file_obj, "buffer", None)
    if buffer_obj is None:
        file_obj.seek(0)
        content = file_obj.read()
        if len(content) <= max_chars:
            return content
        return content[-max_chars:]

    buffer_obj.seek(0, os.SEEK_END)
    end_pos = buffer_obj.tell()
    if end_pos <= 0:
        return ""

    read_size = min(end_pos, max_chars)
    buffer_obj.seek(-read_size, os.SEEK_END)
    chunk = buffer_obj.read(read_size)
    return chunk.decode("utf-8", errors="replace")
