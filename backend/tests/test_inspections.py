from app.inspections import inspection_file_extension


def test_inspection_upload_detects_supported_file_signatures():
    assert inspection_file_extension("application/pdf", b"%PDF-1.7") == ".pdf"
    assert inspection_file_extension("image/jpeg", b"\xff\xd8\xff\xe0") == ".jpg"
    assert inspection_file_extension("image/png", b"\x89PNG\r\n\x1a\n") == ".png"


def test_inspection_upload_rejects_mime_or_signature_mismatch():
    assert inspection_file_extension("text/html", b"%PDF-1.7") is None
    assert inspection_file_extension("image/png", b"<svg></svg>") is None
    assert inspection_file_extension("application/pdf", b"not a pdf") is None
