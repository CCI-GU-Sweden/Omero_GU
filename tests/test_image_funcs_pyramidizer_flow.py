import shutil
from pathlib import Path

import pytest

from common import czi_pyramidizer


TEST_DATA_DIR = Path(__file__).parent / "data"


def _require_pyramidizer_available() -> None:
    try:
        result = czi_pyramidizer.get_version(timeout_sec=15)
    except czi_pyramidizer.CziPyramidizerError as exc:
        pytest.skip(f"czi-pyramidizer not available: {exc}")
        return

    if result.exit_code != czi_pyramidizer.SUCCESS_EXIT_CODE:
        pytest.skip(
            "czi-pyramidizer --version failed "
            f"(exit_code={result.exit_code}, stderr={result.stderr!r})"
        )
        return


def test_980_fixture_is_already_pyramidized():
    _require_pyramidizer_available()

    czi_path = TEST_DATA_DIR / "980-test-image.czi"
    check_result = czi_pyramidizer.check_needs_pyramid(czi_path)

    assert check_result.needs_pyramid is False


def test_700_fixture_gets_pyramidized_then_rechecked(monkeypatch, tmp_path):
    _require_pyramidizer_available()

    source_path = TEST_DATA_DIR / "test_700-conversion.czi"
    working_path = tmp_path / source_path.name
    shutil.copy2(source_path, working_path)

    monkeypatch.setattr(czi_pyramidizer.conf, "CZI_PYRAMIDIZER_THRESHOLD", 1)

    check_before = czi_pyramidizer.check_needs_pyramid(working_path)
    assert check_before.needs_pyramid is True

    build_result = czi_pyramidizer.build_pyramid(working_path, working_path)
    assert build_result.run_result.exit_code in {
        czi_pyramidizer.SUCCESS_EXIT_CODE,
        czi_pyramidizer.NO_ACTION_EXIT_CODE,
    }

    check_after = czi_pyramidizer.check_needs_pyramid(working_path)
    assert check_after.needs_pyramid is False