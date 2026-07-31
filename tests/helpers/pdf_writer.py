"""Build a minimal, real, text-layer PDF from plain lines — no external PDF library.

Used by payment API/E2E tests to exercise the real upload -> pypdfium2 text
extraction path without depending on reportlab (not a project dependency) or a
gitignored real sample file. Verified to round-trip through
`pypdfium2.PdfDocument(...).get_page(0).get_textpage().get_text_range()`.
"""

import io


def make_text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF whose text layer is `lines`, one per text-showing line.

    pypdfium2 (and PDF readers generally) extract text in content-stream order
    for a stream this simple, so the lines come back out in the same order
    they were written in, joined the way a real reader joins text lines
    (`\\r\\n` between rows, verified against this exact generator).
    """
    font_size, leading, y_start = 11, 14, 750
    parts = ["BT", f"/F1 {font_size} Tf", f"{leading} TL", f"50 {y_start} Td"]
    for i, line in enumerate(lines):
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if i:
            parts.append("T*")
        parts.append(f"({escaped}) Tj")
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n".encode())
        buf.write(obj)
        buf.write(b"\nendobj\n")
    xref_offset = buf.tell()
    n = len(objects) + 1
    buf.write(f"xref\n0 {n}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(b"trailer\n")
    buf.write(f"<< /Size {n} /Root 1 0 R >>\n".encode())
    buf.write(b"startxref\n")
    buf.write(f"{xref_offset}\n".encode())
    buf.write(b"%%EOF")
    return buf.getvalue()


def make_blank_pdf() -> bytes:
    """A structurally valid one-page PDF with an empty content stream — no text
    layer at all, the "scanned image" case `pdf_text.extract_text` must reject.
    """
    return make_text_pdf([])
