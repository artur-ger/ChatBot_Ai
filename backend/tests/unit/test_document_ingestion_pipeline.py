from pathlib import Path

import pytest

from app.core.errors import ValidationAppError
from app.services.ingestion_service import save_upload_to_temp
from app.services.text_chunking import chunk_segments
from app.services.text_extract import ExtractedTextSegment, extract_text_segments_from_file


def test_extract_txt_detects_cp1251_encoding(tmp_path: Path) -> None:
    source = "Вопрос: Что ты умеешь?\n\nОтвет: Я помогаю инвесторам и эмитентам платформы."
    path = tmp_path / "knowledge.txt"
    path.write_bytes(source.encode("cp1251"))

    segments = extract_text_segments_from_file(path=path, doc_type="text")

    assert [segment.text for segment in segments] == [
        "Вопрос: Что ты умеешь?",
        "Ответ: Я помогаю инвесторам и эмитентам платформы.",
    ]


def test_chunk_segments_uses_word_limits_overlap_and_metadata() -> None:
    words = [f"слово{i}" for i in range(1, 76)]
    segments = [ExtractedTextSegment(text=" ".join(words), page_number=3)]

    chunks = chunk_segments(
        segments,
        chunk_size_words=30,
        overlap_words=5,
        min_words=20,
    )

    assert [chunk.word_count for chunk in chunks] == [30, 30, 25]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert all(chunk.page_number == 3 for chunk in chunks)
    assert chunks[0].text.split()[-5:] == chunks[1].text.split()[:5]


@pytest.mark.asyncio
async def test_upload_validation_rejects_eicar_payload() -> None:
    payload = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

    with pytest.raises(ValidationAppError):
        await save_upload_to_temp(
            filename="bad.txt",
            declared_content_type="text/plain",
            file_bytes=payload,
        )
