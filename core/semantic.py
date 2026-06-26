"""ChromaDB-backed semantic memory for facts.

Wraps a persistent Chroma collection so facts can be recalled by meaning, not
just keyword overlap. The SQLite `facts` table remains the source of truth;
this is an index on top. All methods degrade to raising so callers can fall
back to keyword recall if Chroma is unavailable.
"""

from __future__ import annotations

from pathlib import Path


class SemanticStore:
    def __init__(self, chroma_dir: str | Path, embedding_function=None):
        import chromadb  # lazy: heavy import

        self.client = chromadb.PersistentClient(path=str(chroma_dir))
        # Default embedding function (all-MiniLM via onnxruntime) is fetched
        # on first use; no API key required. A custom one can be injected
        # (e.g. for tests or to avoid the model download).
        kwargs = {}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        self.collection = self.client.get_or_create_collection("facts", **kwargs)

    def add(self, fact_id: int, fact: str, category: str = "other") -> None:
        self.collection.upsert(
            ids=[str(fact_id)],
            documents=[fact],
            metadatas=[{"category": category}],
        )

    def query(self, text: str, k: int = 8) -> list[dict]:
        n = max(1, min(k, max(1, self.count())))
        res = self.collection.query(query_texts=[text], n_results=n)
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        out = []
        for i, d, m in zip(ids, docs, metas):
            out.append({
                "id": int(i),
                "fact": d,
                "category": (m or {}).get("category", "other"),
            })
        return out

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0
