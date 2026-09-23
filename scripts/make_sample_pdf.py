"""Generate examples/sample-msa.pdf from examples/sample-msa.md.

Run once:  python3 scripts/make_sample_pdf.py
Uses pypdf to build a minimal text-layer PDF (no scanned images), so tests can
verify the PDF ingestion path end-to-end.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

ROOT = Path(__file__).resolve().parent.parent
PAGE_W, PAGE_H = 612, 792
MARGIN, FONT_SIZE, LEADING = 72, 11, 15
MAX_CHARS = 95


def pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_stream(lines: list[str]) -> DecodedStreamObject:
    ops = [f"BT /F1 {FONT_SIZE} Tf {MARGIN} {PAGE_H - MARGIN} Td {LEADING} TL"]
    for line in lines:
        ops.append(f"({pdf_escape(line)}) Tj T*")
    ops.append("ET")
    stream = DecodedStreamObject()
    stream.set_data(" ".join(ops).encode("latin-1"))
    return stream


def main() -> None:
    raw = (ROOT / "examples" / "sample-msa.md").read_text(encoding="utf-8")
    # Flatten markdown to plain text lines; keep headings as-is minus '#'.
    flat: list[str] = []
    for para in raw.split("\n\n"):
        para = para.replace("\n", " ").strip()
        if para.startswith("#"):
            para = para.lstrip("# ")
        for chunk in textwrap.wrap(para, width=MAX_CHARS) or [""]:
            flat.append(chunk)
        flat.append("")

    lines_per_page = (PAGE_H - 2 * MARGIN) // LEADING
    chunks = [flat[i : i + lines_per_page] for i in range(0, len(flat), lines_per_page)]

    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for chunk in chunks:
        page = writer.add_blank_page(width=PAGE_W, height=PAGE_H)
        page[NameObject("/Contents")] = page_stream(chunk)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        page[NameObject("/MediaBox")] = ArrayObject(
            [NumberObject(0), NumberObject(0), NumberObject(PAGE_W), NumberObject(PAGE_H)]
        )

    out = ROOT / "examples" / "sample-msa.pdf"
    with out.open("wb") as f:
        writer.write(f)
    print(f"wrote {out} ({len(chunks)} page(s))")


if __name__ == "__main__":
    main()
