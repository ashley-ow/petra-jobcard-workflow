from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from .models import ReferenceChunk

_WHITESPACE = re.compile(r"[ \t]+")


def extract_pdf_chunks(
    path: Path,
    document_id: str,
    source_file: str,
    chunk_chars: int,
    overlap: int,
) -> list[ReferenceChunk]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - library raises several types
            raise ValueError("Password-protected PDFs are not supported by this sample.") from exc

    chunks: list[ReferenceChunk] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = normalize_page_text(page.extract_text() or "")
        if not text:
            continue
        for chunk_number, content in enumerate(chunk_text(text, chunk_chars, overlap), start=1):
            chunks.append(
                ReferenceChunk(
                    chunk_id=f"{document_id}-p{page_number:05d}-c{chunk_number:04d}",
                    document_id=document_id,
                    source_file=source_file,
                    page_number=page_number,
                    chunk_number=chunk_number,
                    content=content,
                )
            )

    if not chunks:
        raise ValueError(
            "The PDF contains no extractable text. Run OCR first or add Azure Document Intelligence OCR."
        )
    return chunks


def normalize_page_text(text: str) -> str:
    lines = []
    for line in text.replace("\x00", "").splitlines():
        cleaned = _WHITESPACE.sub(" ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    if chunk_chars < 200:
        raise ValueError("chunk_chars must be at least 200")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap must be non-negative and smaller than chunk_chars")

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        target = min(start + chunk_chars, length)
        end = target
        if target < length:
            candidates = [text.rfind("\n", start + chunk_chars // 2, target), text.rfind(" ", start + chunk_chars // 2, target)]
            boundary = max(candidates)
            if boundary > start:
                end = boundary
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end >= length:
            break
        start = max(start + 1, end - overlap)
    return chunks
