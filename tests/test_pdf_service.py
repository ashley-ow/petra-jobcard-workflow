from backend.app.pdf_service import chunk_text, normalize_page_text


def test_chunk_text_has_overlap_and_preserves_content() -> None:
    text = " ".join(f"token-{index}" for index in range(500))
    chunks = chunk_text(text, chunk_chars=300, overlap=50)
    assert len(chunks) > 2
    assert all(chunks)
    assert "token-0" in chunks[0]
    assert "token-499" in chunks[-1]


def test_normalize_page_text() -> None:
    raw = "Task A\t  5 mandays\n\nTask B    8 mandays\x00"
    assert normalize_page_text(raw) == "Task A 5 mandays\nTask B 8 mandays"
