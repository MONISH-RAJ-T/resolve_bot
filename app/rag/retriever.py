"""Policy search: a custom LangChain retriever that ranks sections with BM25 (rank_bm25).
Runs on any CPU and needs no extra API calls."""
import re
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from rank_bm25 import BM25Okapi

from app.core import config
from app.rag.loader import usable_documents
from app.rules import dates

STOP = set("a an the of to in on for and or is are be do does can i my me you your it this that with as at by from if "
           "how what when which who will we our any many much long take takes something anything want need get have has".split())


def stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "edly", "ed", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if len(w) > 4 and w[-1] in "ey":
        w = w[:-1]
    if len(w) > 3 and w[-1] == w[-2]:
        w = w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


class PolicyRetriever(BaseRetriever):
    """Returns the best-matching policy sections. Sections with no match at all are dropped."""
    docs: list[Document]
    bm25: Any
    k: int = 5

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        tokens = tokenize(query)
        if not tokens or not self.docs or self.bm25 is None:
            return []
        ranked = []
        for doc, score in zip(self.docs, self.bm25.get_scores(tokens)):
            if score > 0:
                if doc.metadata["doc_type"] == "faq":
                    score *= 0.7  # policies outrank the FAQ summaries
                ranked.append((score, doc))
        ranked.sort(key=lambda x: -x[0])
        return [d for _, d in ranked[: self.k]]


@lru_cache(maxsize=4)
def _retriever(today_iso: str) -> PolicyRetriever:
    docs = usable_documents(dates.today())
    bm25 = BM25Okapi([tokenize(d.page_content) for d in docs]) if docs else None  # title + heading are searchable too
    return PolicyRetriever(docs=docs, bm25=bm25)


def search(query: str, k: int = 5) -> list[dict]:
    """Best sections for a query, each with doc_id and section (used for citations)."""
    retriever = _retriever(config.APP_TODAY)
    retriever.k = k
    results = []
    for doc in retriever.invoke(query):
        m = doc.metadata
        item = {"doc_id": m["doc_id"], "section": m["section"], "title": m["title"], "heading": m["heading"],
                "doc_type": m["doc_type"], "status": m["applies"], "effective_date": m["effective_date"],
                "text": m["body"]}
        if m["applies"] == "future_change":
            item["note"] = f"NOT IN EFFECT YET. Starts {m['effective_date']}. Mention only as an upcoming change."
        results.append(item)
    return results
