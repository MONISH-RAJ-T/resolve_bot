"""Tool 2: search_policy. Only current, already-started documents are searched (see app/rag)."""
from app.rag import retriever


def search_policy(query: str = "") -> dict:
    results = retriever.search(str(query))
    if not results:
        return {"results": [], "note": "No current policy document answers this."}
    return {"results": results}
