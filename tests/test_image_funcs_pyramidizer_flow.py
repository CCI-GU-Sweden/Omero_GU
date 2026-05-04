from common import image_funcs
from common import czi_pyramidizer
from common.file_data import FileData


def _make_file_data(main_path: str, total_size: int = 0) -> FileData:
    fd = FileData([main_path])
    fd.setTempFilePaths([main_path])
    fd.setFileSizes([total_size])
    return fd


def test_file_format_splitter_uses_pyramidizer_when_enabled(monkeypatch):
    file_path = "tests/data/test_image.czi"
    file_data = _make_file_data(file_path, total_size=1024)

    check_result = czi_pyramidizer.CziPyramidCheckResult(
        needs_pyramid=True,
        run_result=czi_pyramidizer.CziPyramidizerRunResult(
            command=("czi-pyramidizer",),
            exit_code=czi_pyramidizer.PYRAMID_NEEDED_EXIT_CODE,
            stdout="",
            stderr="",
        ),
    )
    build_result = czi_pyramidizer.CziPyramidBuildResult(
        created_output=True,
        run_result=czi_pyramidizer.CziPyramidizerRunResult(
            command=("czi-pyramidizer",),
            exit_code=czi_pyramidizer.SUCCESS_EXIT_CODE,
            stdout="",
            stderr="",
        ),
    )

    monkeypatch.setattr(image_funcs, "get_info_metadata_from_czi", lambda _: {"Microscope": "LSM 700"})
    monkeypatch.setattr(image_funcs.czi_pyramidizer, "check_needs_pyramid", lambda _: check_result)
    monkeypatch.setattr(image_funcs.czi_pyramidizer, "build_pyramid", lambda *_args, **_kwargs: build_result)
    monkeypatch.setattr(image_funcs.conf, "CZI_PYRAMIDIZER_ENABLED", True)
    monkeypatch.setattr(image_funcs.conf, "CZI_PYRAMIDIZER_FALLBACK_TO_OLD_CONVERSION", False)

    converted, metadata = image_funcs.file_format_splitter(file_data)

    assert converted == [file_path]
    assert metadata["Microscope"] == "LSM 700"


def test_file_format_splitter_uses_legacy_fallback_on_pyramidizer_error(monkeypatch):
    file_path = "tests/data/test_image.czi"
    file_data = _make_file_data(file_path, total_size=1024)

    run_result = czi_pyramidizer.CziPyramidizerRunResult(
        command=("czi-pyramidizer",),
        exit_code=czi_pyramidizer.GENERAL_FAILURE_EXIT_CODE,
        stdout="",
        stderr="err",
    )

    monkeypatch.setattr(image_funcs, "get_info_metadata_from_czi", lambda _: {"Microscope": "LSM 700"})
    monkeypatch.setattr(
        image_funcs.czi_pyramidizer,
        "check_needs_pyramid",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            czi_pyramidizer.CziPyramidizerError("failed", run_result=run_result)
        ),
    )
    monkeypatch.setattr(image_funcs, "_convert_czi_with_legacy_policy", lambda *_args, **_kwargs: ["legacy.ome.tiff"])
    monkeypatch.setattr(image_funcs.conf, "CZI_PYRAMIDIZER_ENABLED", True)
    monkeypatch.setattr(image_funcs.conf, "CZI_PYRAMIDIZER_FALLBACK_TO_OLD_CONVERSION", True)

    converted, _ = image_funcs.file_format_splitter(file_data)

    assert converted == ["legacy.ome.tiff"]