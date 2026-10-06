from backend.app.storage import safe_filename


def test_safe_filename_removes_path_and_unsafe_characters() -> None:
    assert safe_filename("../../My reference (final).pdf") == "My-reference-final-.pdf"
