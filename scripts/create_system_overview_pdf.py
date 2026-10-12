from pathlib import Path
import textwrap


SOURCE = Path("docs/system-overview.md")
OUTPUT = Path("docs/agentic-revenue-system-overview.pdf")


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_lines() -> list[str]:
    result: list[str] = []
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw.replace("**", "").replace("`", "")
        if line.startswith("#"):
            line = line.lstrip("# ").upper()
            result.extend(["", line, ""])
        elif line.startswith("- "):
            result.append("• " + line[2:])
        elif line.startswith("| ") or line.startswith("```"):
            result.append(line)
        elif not line.strip():
            result.append("")
        else:
            result.extend(textwrap.wrap(line, width=88) or [""])
    return result


def build() -> bytes:
    pages: list[list[str]] = []
    current: list[str] = []
    for line in text_lines():
        current.append(line)
        if len(current) >= 48:
            pages.append(current)
            current = []
    if current:
        pages.append(current)

    objects: list[bytes] = []
    page_ids: list[int] = []
    font_id = 3
    for page in pages:
        commands = ["BT", "/F1 9.5 Tf", "50 750 Td"]
        for index, line in enumerate(page):
            if index:
                commands.append("0 -15 Td")
            commands.append(f"({esc(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content_id = 4 + len(objects)
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = 4 + len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode())
        page_ids.append(page_id)

    pages_kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.insert(0, f"<< /Type /Pages /Kids [{pages_kids}] /Count {len(page_ids)} >>".encode())
    objects.insert(0, b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.insert(2, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    startxref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode())
    return bytes(pdf)


OUTPUT.write_bytes(build())
print(OUTPUT)
