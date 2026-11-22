from __future__ import annotations

import pytest

from app.paths import (
    PathValidationError,
    safe_join,
    sanitize_filename,
    sanitize_path,
    sanitize_segment,
    unique_filename,
)


@pytest.mark.parametrize("value", ["..", ".", "", "   ", "..."])
def test_unsafe_segments_rejected(value):
    with pytest.raises(PathValidationError):
        sanitize_segment(value)


def test_segment_sanitizes_and_handles_reserved_names():
    assert sanitize_segment('a<b>c:d"e|f?g*h') == "a_b_c_d_e_f_g_h"
    assert sanitize_segment("CON") == "_CON"
    assert sanitize_segment("  Report   Final  ") == "Report Final"
    assert len(sanitize_segment("x" * 200)) <= 60


def test_filename_strict_mode_rejects_paths():
    with pytest.raises(PathValidationError):
        sanitize_filename("../../etc/passwd", strict=True)
    with pytest.raises(PathValidationError):
        sanitize_filename("C:\\Windows\\evil.exe", strict=True)
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("report.pdf") == "report.pdf"


def test_path_validation_depth_and_traversal():
    assert sanitize_path(["Career", "Career", "Resumes"]) == ["Career", "Resumes"]
    with pytest.raises(PathValidationError):
        sanitize_path(["a", "b", "c", "d", "e"])
    with pytest.raises(PathValidationError):
        sanitize_path(["..", "etc"], strict=True)
    with pytest.raises(PathValidationError):
        sanitize_path(["C:\\Windows"], strict=True)


def test_safe_join_blocks_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert safe_join(root, "Inbox/a.txt") == (root / "Inbox" / "a.txt").resolve()
    with pytest.raises(PathValidationError):
        safe_join(root, "../outside.txt")
    with pytest.raises(PathValidationError):
        safe_join(root, str(tmp_path / "outside.txt"))


def test_unique_filename_collision(tmp_path):
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "Report.pdf").write_bytes(b"x")
    assert unique_filename(directory, "Report.pdf") == "Report (2).pdf"
    (directory / "Report (2).pdf").write_bytes(b"x")
    assert unique_filename(directory, "Report.pdf") == "Report (3).pdf"
    assert unique_filename(directory, "Report.pdf", taken={"report.pdf"}) == "Report (3).pdf"
