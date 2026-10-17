"""Optional semantic retrieval with sentence-transformers.

This is an *optional* signal. If ``sentence-transformers`` is not installed (the
default install), ``SemanticSearcher.available`` is False, the semantic weight is
ignored, and the UI/API report that semantic retrieval is unavailable. ACWM never
reports semantic scores it did not compute.

Note: the first use downloads the embedding model from Hugging Face. This path is
not exercised by the default test suite.
"""

from __future__ import annotations

import importlib.util

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def semantic_dependencies_installed() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


class SemanticSearcher:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self.available = semantic_dependencies_installed()
        self.reason = (
            ""
            if self.available
            else (
                "sentence-transformers is not installed (pip install -r requirements-optional.txt)"
            )
        )
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def score(self, query: str, documents: dict[str, str]) -> dict[str, float]:
        """Cosine similarity mapped to [0, 1] per document path."""
        if not self.available or not documents:
            return {}
        try:
            model = self._load()
            paths = sorted(documents)
            doc_emb = model.encode([documents[p][:4000] for p in paths], normalize_embeddings=True)
            q_emb = model.encode([query], normalize_embeddings=True)[0]
        except Exception as exc:  # noqa: BLE001 - model download/runtime failures
            self.available = False
            self.reason = f"semantic model failed to load/run: {type(exc).__name__}"
            return {}
        sims = doc_emb @ q_emb
        return {p: float(max(0.0, min(1.0, (s + 1) / 2))) for p, s in zip(paths, sims, strict=True)}
