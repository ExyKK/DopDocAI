from app.worker.snapshot_resolver import _parse_ls_tree_line


def test_parse_ls_tree_line_skips_symlink_blob() -> None:
    assert (
        _parse_ls_tree_line(
            "120000 blob aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 8\t"
            "internal/reader/readability/testdata"
        )
        is None
    )


def test_parse_ls_tree_line_keeps_regular_file_blob() -> None:
    parsed = _parse_ls_tree_line(
        "100644 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 42\t"
        "internal/reader/readability/readability.go"
    )

    assert parsed is not None
    assert parsed.path == "internal/reader/readability/readability.go"
    assert parsed.size == 42
