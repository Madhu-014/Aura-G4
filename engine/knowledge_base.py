"""Local ChromaDB knowledge base for offline emergency manuals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import hashlib
import re

import chromadb
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer


@dataclass
class KnowledgeSnippet:
    """Retrieved snippet and metadata."""

    manual_name: str
    snippet: str
    page: int
    score: float


class AuraKnowledge:
    """Offline vector store and retrieval for emergency protocol manuals."""

    def __init__(self, data_dir: str, db_dir: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.db_dir = Path(db_dir or (self.data_dir / "chroma_store"))
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.db_dir))
        self.collection = self.client.get_or_create_collection(name="aura_protocols")
        # CPU device keeps unified GPU memory available for Gemma runs.
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = text.replace("\x00", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _split_chunks(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = max(0, end - overlap)
        return chunks

    @staticmethod
    def _id_for_chunk(path: Path, page_idx: int, chunk_idx: int, text: str) -> str:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return f"{path.stem}_p{page_idx}_c{chunk_idx}_{digest}"

    @staticmethod
    def _discover_pdf_files(directory: Path) -> List[Path]:
        """Find PDFs in the given directory and common manuals subfolders."""
        # Primary behavior: recursive scan handles nested structures like data/triage_manuals/*.pdf
        pdfs = sorted(path for path in directory.rglob("*.pdf") if path.is_file())
        if pdfs:
            return pdfs

        # Fallback for common naming variations if a custom directory is passed.
        manual_dirs = ["triage_manuals", "traige_manuals", "manuals"]
        fallback: List[Path] = []
        for name in manual_dirs:
            candidate = directory / name
            if candidate.exists() and candidate.is_dir():
                fallback.extend(path for path in candidate.rglob("*.pdf") if path.is_file())
        return sorted(fallback)

    def ingest_manuals(self, directory_path: str) -> Dict[str, Any]:
        """Parse all PDFs in the directory and upsert vectorized snippets."""
        directory = Path(directory_path)
        pdf_files = self._discover_pdf_files(directory)

        total_chunks = 0
        loaded_manuals: List[str] = []

        for pdf_path in pdf_files:
            try:
                reader = PdfReader(str(pdf_path))
            except Exception:
                continue

            docs: List[str] = []
            metas: List[Dict[str, Any]] = []
            ids: List[str] = []

            for page_idx, page in enumerate(reader.pages):
                page_text = self._normalize_text(page.extract_text() or "")
                if not page_text:
                    continue
                chunks = self._split_chunks(page_text)
                for chunk_idx, chunk in enumerate(chunks):
                    chunk_id = self._id_for_chunk(pdf_path, page_idx + 1, chunk_idx, chunk)
                    ids.append(chunk_id)
                    docs.append(chunk)
                    metas.append(
                        {
                            "manual_name": pdf_path.name,
                            "page": page_idx + 1,
                        }
                    )

            if not docs:
                continue

            # Small batches reduce memory spikes on low-power edge hardware.
            batch_size = 32
            for i in range(0, len(docs), batch_size):
                b_docs = docs[i : i + batch_size]
                b_metas = metas[i : i + batch_size]
                b_ids = ids[i : i + batch_size]
                embeddings = self.embedder.encode(b_docs, convert_to_numpy=True, normalize_embeddings=True)
                self.collection.upsert(
                    ids=b_ids,
                    documents=b_docs,
                    metadatas=b_metas,
                    embeddings=embeddings.tolist(),
                )

            total_chunks += len(docs)
            loaded_manuals.append(pdf_path.name)

        return {
            "manual_count": len(loaded_manuals),
            "chunk_count": total_chunks,
            "manuals": loaded_manuals,
        }

    def query_protocols(self, user_query: str, top_k: int = 3) -> List[KnowledgeSnippet]:
        """Retrieve top protocol snippets for a user query."""
        query = self._normalize_text(user_query)
        if not query:
            return []

        query_vector = self.embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
        result = self.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k,
        )

        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        snippets: List[KnowledgeSnippet] = []
        for idx, doc in enumerate(docs):
            if not doc:
                continue
            meta = metas[idx] if idx < len(metas) else {}
            distance = float(distances[idx]) if idx < len(distances) else 0.0
            snippets.append(
                KnowledgeSnippet(
                    manual_name=str(meta.get("manual_name", "Unknown Manual")),
                    snippet=str(doc),
                    page=int(meta.get("page", 0) or 0),
                    score=max(0.0, 1.0 - distance),
                )
            )
        return snippets

    def list_loaded_manuals(self) -> List[str]:
        """List unique manual names currently indexed in ChromaDB."""
        result = self.collection.get(include=["metadatas"])
        names = {meta.get("manual_name", "Unknown Manual") for meta in result.get("metadatas", [])}
        return sorted(str(name) for name in names)
