"""File signature checks for private inspection evidence."""


def inspection_file_extension(content_type: str, header: bytes) -> str | None:
    signatures = {
        "application/pdf": (b"%PDF-", ".pdf"),
        "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
        "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    }
    signature = signatures.get(content_type.lower().split(";", 1)[0].strip())
    if signature is None or not header.startswith(signature[0]):
        return None
    return signature[1]
