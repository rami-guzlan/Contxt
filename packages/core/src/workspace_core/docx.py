"""A Word document (.docx) from Markdown, with the standard library only.

Enough for a Workspace doc to leave the app as Word: a title, headings (#, ##, ###), paragraphs,
bulleted and numbered lines, quotes, and **bold** inside a line. Anything else (tables, images,
links) goes in as its text. Word, Google Docs and Pages open it; the Brain's own reader reads
it back the same way it reads any .docx.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)
DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>'
)


def _style(style_id: str, name: str, size: int, bold: bool, before: int, after: int) -> str:
    weight = "<w:b/>" if bold else ""
    return (
        f'<w:style w:type="paragraph" w:styleId="{style_id}"><w:name w:val="{name}"/>'
        '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:keepNext/><w:spacing w:before="{before}" w:after="{after}"/></w:pPr>'
        f'<w:rPr>{weight}<w:sz w:val="{size}"/></w:rPr></w:style>'
    )


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W}">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:pPr><w:spacing w:after="120"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>'
    + _style("Title", "Title", 40, True, 0, 240)
    + _style("Heading1", "heading 1", 32, True, 360, 120)
    + _style("Heading2", "heading 2", 26, True, 240, 80)
    + _style("Heading3", "heading 3", 23, True, 200, 60)
    + '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="567"/></w:pPr>'
    "<w:rPr><w:i/></w:rPr></w:style>"
    "</w:styles>"
)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s+)?(.*)$")
NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
LINK = re.compile(r"!?\[([^\]]*)\]\(([^)]*)\)")


def _runs(text: str) -> str:
    """A line's text as Word runs: **bold** parts bold, links as their words, the rest plain."""
    text = LINK.sub(lambda m: m.group(1) or m.group(2), text)
    out, last = [], 0
    for found in BOLD.finditer(text):
        if found.start() > last:
            out.append(_run(text[last : found.start()]))
        out.append(_run(found.group(1), bold=True))
        last = found.end()
    if last < len(text):
        out.append(_run(text[last:]))
    return "".join(out)


def _run(text: str, *, bold: bool = False) -> str:
    plain = text.replace("`", "").replace("__", "")
    props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(plain)}</w:t></w:r>'


def _paragraph(text: str, style: str | None = None, indent: int = 0) -> str:
    props = ""
    if style or indent:
        inner = (f'<w:pStyle w:val="{style}"/>' if style else "") + (
            f'<w:ind w:left="{indent}" w:hanging="283"/>' if indent else ""
        )
        props = f"<w:pPr>{inner}</w:pPr>"
    return f"<w:p>{props}{_runs(text)}</w:p>"


def markdown_to_docx(title: str, markdown: str) -> bytes:
    """The Word file: the title first, then the Markdown, paragraph by paragraph."""
    paragraphs = [_paragraph(title, "Title")] if title.strip() else []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            paragraphs.append(_paragraph(" ".join(line.strip() for line in buffer)))
            buffer.clear()

    for line in str(markdown or "").splitlines():
        if not line.strip():
            flush()
            continue
        heading = HEADING.match(line)
        bullet = BULLET.match(line)
        numbered = NUMBERED.match(line)
        if heading:
            flush()
            level = min(len(heading.group(1)), 3)
            paragraphs.append(_paragraph(heading.group(2).strip(), f"Heading{level}"))
        elif bullet:
            flush()
            paragraphs.append(_paragraph("• " + bullet.group(1).strip(), indent=567))
        elif numbered:
            flush()
            paragraphs.append(
                _paragraph(f"{numbered.group(1)}. {numbered.group(2).strip()}", indent=567)
            )
        elif line.lstrip().startswith(">"):
            flush()
            paragraphs.append(_paragraph(line.lstrip()[1:].strip(), "Quote"))
        else:
            buffer.append(line)
    flush()
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>'
        + "".join(paragraphs)
        + "<w:sectPr/></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", RELS)
        package.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        package.writestr("word/styles.xml", STYLES)
        package.writestr("word/document.xml", document)
    return out.getvalue()
