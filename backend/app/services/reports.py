# Owner: Dev B (rendering filled in by Dev C)
"""Report rendering. The PDF writer is a dependency-free placeholder for Dev C to replace."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd


def to_xlsx(rows: list[dict[str, Any]], sheet: str = "report") -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, sheet_name=sheet)
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def to_pdf(title: str, lines: list[str]) -> bytes:
    """Write a minimal one-page PDF with a title and plain text lines."""
    text = ["BT", "/F1 16 Tf", "50 790 Td", f"({_pdf_escape(title)}) Tj", "/F1 10 Tf"]
    for line in lines[:60]:
        text += ["0 -14 Td", f"({_pdf_escape(line)}) Tj"]
    text.append("ET")
    stream = "\n".join(text).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)
