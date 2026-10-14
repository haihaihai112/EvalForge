import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024


def import_document(name, content):
    if len(content) > MAX_BYTES:
        raise ValueError("文档不能超过 8 MB")
    suffix = Path(name).suffix.lower()
    if suffix in (".txt", ".md"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT/MD 请保存为 UTF-8 编码") from exc
    elif suffix == ".pdf":
        from pypdf import PdfReader
        try:
            pdf = PdfReader(io.BytesIO(content))
            if len(pdf.pages) > 300:
                raise ValueError("PDF 最多 300 页")
            text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as exc:
            raise ValueError("无法读取 PDF；请确认文件有效且未加密") from exc
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 16 * 1024 * 1024:
                    raise ValueError("DOCX 解压后文本过大")
                root = ET.fromstring(archive.read(info))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "\n\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
        except Exception as exc:
            raise ValueError("无法读取 DOCX；请确认文件有效") from exc
    else:
        raise ValueError("支持 UTF-8 TXT、MD、文本 PDF 和 DOCX")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < 30:
        raise ValueError("文档有效文字不足 30 字；扫描 PDF 请先 OCR")
    if len(text) > 150000:
        raise ValueError("文档文字最多 150,000 字，请按章节拆分")
    digest = hashlib.sha256(text.encode()).hexdigest()
    doc_id = "doc_" + digest[:16]
    chunks = []
    for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        for offset in range(0, len(match.group()), 1400):
            part = match.group()[offset:offset + 1400].strip()
            if len(part) < 8 or (part.startswith("# ") and len(part) < 60):
                continue
            start = text.find(part, match.start() + offset)
            chunks.append({"id": f"{doc_id}:{len(chunks)+1}", "text": part,
                           "start": start, "end": start + len(part), "source": Path(name).name})
    if not chunks:
        raise ValueError("无法提取有效条款，请检查段落结构")
    return {"id": doc_id, "name": Path(name).name, "text": text, "sha256": digest, "chunks": chunks}
