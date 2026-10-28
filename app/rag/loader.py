"""Turns policies.md + manifest.json into LangChain Documents (one per ### section).
Each Document carries its doc_id, section and manifest data as metadata."""
import json
import re
from datetime import date
from functools import lru_cache

from langchain_core.documents import Document

from app.core import config

DOC_ID_RE = re.compile(r"\*\*Document ID:\*\*\s*([A-Za-z0-9_\-]+)")
H2_RE = re.compile(r"^##\s+(?:§[\d.]+\s+)?(.*)$")
H3_RE = re.compile(r"^###\s+(§[\d.]+)\s+(.*)$")


@lru_cache(maxsize=1)
def load_documents() -> list[Document]:
    """All sections of all documents listed in the manifest (status and date are applied later)."""
    with open(config.MANIFEST_PATH, encoding="utf-8") as f:
        manifest = {m["doc_id"]: m for m in json.load(f)}
    with open(config.POLICIES_PATH, encoding="utf-8") as f:
        lines = f.read().splitlines()

    # split the big file into documents at each "# " title line
    raw_docs, cur = [], None
    for line in lines:
        if line.startswith("# "):
            cur = {"title": line[2:].strip(), "lines": []}
            raw_docs.append(cur)
        elif cur is not None:
            cur["lines"].append(line)

    documents = []
    for raw in raw_docs:
        m = DOC_ID_RE.search("\n".join(raw["lines"]))
        meta = manifest.get(m.group(1)) if m else None
        if not meta:
            continue  # a document missing from the manifest is never usable
        state = {"h2": "", "section": None, "body": []}

        def flush():
            if state["section"]:
                text = "\n".join(state["body"]).strip()
                number, name = state["section"]
                heading = f"{state['h2']} / {name}" if state["h2"] else name
                documents.append(Document(
                    page_content=f"{raw['title']}\n{heading}\n{text}",
                    metadata={"doc_id": meta["doc_id"], "section": number, "title": raw["title"],
                              "heading": heading, "doc_type": meta.get("doc_type", "policy"),
                              "status": meta.get("status"), "effective_date": meta.get("effective_date"),
                              "body": text}))

        for line in raw["lines"]:
            h3 = H3_RE.match(line)
            if h3:
                flush()
                state["section"], state["body"] = (h3.group(1), h3.group(2).strip()), []
            elif line.startswith("## "):
                flush()
                h2 = H2_RE.match(line)
                state["section"], state["body"], state["h2"] = None, [], (h2.group(1).strip() if h2 else "")
            elif state["section"]:
                state["body"].append(line)
        flush()
    return documents


def applies(doc: Document, today: date) -> str | None:
    """'in_effect', 'future_change', or None (superseded or bad date)."""
    if doc.metadata.get("status") != "current":
        return None
    try:
        start = date.fromisoformat(doc.metadata["effective_date"])
    except (TypeError, ValueError, KeyError):
        return None
    return "in_effect" if start <= today else "future_change"


def usable_documents(today: date) -> list[Document]:
    """Only current documents. Tagged 'applies' = in_effect (already started) or future_change (starts later)."""
    out = []
    for d in load_documents():
        state = applies(d, today)
        if state:
            out.append(Document(page_content=d.page_content, metadata={**d.metadata, "applies": state}))
    return out
