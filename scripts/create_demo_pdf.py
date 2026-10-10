from pathlib import Path


lines = [
    "DEMO AGREEMENT - NOT FOR COMMERCIAL USE",
    "",
    "This fictional agreement is provided only for testing the Agentic Revenue System",
    "and Dropbox Sign sandbox integration. It creates no commercial obligation.",
    "",
    "Customer: Example Foods",
    "Supplier: Agentic Revenue System Demo",
    "Service: Campaign activation and measurement planning",
    "Budget: USD 250,000",
    "Start date: November 1, 2026",
    "End date: January 31, 2027",
    "",
    "TEST SIGNER",
    "Name: Replace with your own test signer name",
    "Email: Replace with your own test signer email",
    "",
    "SIGNATURE",
    "Signature: __________________________________________",
    "Date: _______________________________________________",
    "",
    "DEMO NOTICE: This document contains fictional data and is not legal advice.",
]


def pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf() -> bytes:
    commands = ["BT", "/F1 11 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -22 Td")
        commands.append(f"({pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
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


Path("fixtures/demo-agreement.pdf").write_bytes(build_pdf())
