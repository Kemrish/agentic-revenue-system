"""Immutable, reproducible DOCX artifacts bound to reviewed text and signer.

No remote URL or global signer can replace an approved deal's document.
DOCX uses the standard library only and preserves Unicode agreement text.
"""

import base64
import hashlib
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from revenue_system.agents.deal_desk import IODraft
from revenue_system.skills.io_validation import validate_io

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def render_docx(text: str) -> bytes:
    if not isinstance(text, str) or not text.strip() or len(text) > 500000:
        raise ValueError("A bounded, nonempty contract document is required")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ValueError("Contract contains invalid document characters")
    paragraphs = "".join('<w:p><w:r><w:t xml:space="preserve">' + escape(line) + '</w:t></w:r></w:p>'
                         for line in text.split("\n"))
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '<w:sectPr/></w:body></w:document>',
    }
    output = BytesIO()
    with ZipFile(output, "w", ZIP_STORED) as archive:
        for name, content in files.items():
            # Fixed ZIP metadata makes regeneration identical across machines.
            archive.writestr(ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content.encode("utf-8"))
    return output.getvalue()


def bind_contract(payload: dict, signer_email: str, signer_name: str) -> dict:
    artifact = render_docx(payload["document"])
    return payload | {"artifact_base64": base64.b64encode(artifact).decode("ascii"),
                      "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                      "signer_email": signer_email, "signer_name": signer_name}


def validate_contract(payload: dict) -> bytes:
    """Called at approval AND delivery. Legacy/unbound contracts fail closed."""
    if not isinstance(payload, dict):
        raise ValueError("A reviewed contract artifact and signer are required")
    draft = IODraft.model_validate(payload)
    errors = validate_io(draft.as_io_data())
    if errors:
        raise ValueError("Invalid commercial terms: " + "; ".join(errors))
    email = payload.get("signer_email", "")
    if not isinstance(email, str) or email.count("@") != 1 or any(c.isspace() for c in email) or not payload.get("signer_name", "").strip():
        raise ValueError("Review the deal's signer email and name before approval")
    try:
        artifact = base64.b64decode(payload.get("artifact_base64", ""), validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid contract artifact encoding") from exc
    if hashlib.sha256(artifact).hexdigest() != payload.get("artifact_sha256"):
        raise ValueError("Contract artifact fingerprint mismatch; regenerate and review")
    if artifact != render_docx(payload.get("document", "")):
        raise ValueError("Contract artifact differs from the reviewed document")
    return artifact
