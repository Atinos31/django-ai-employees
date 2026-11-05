"""
Company knowledge base for RAG, stored in ChromaDB.

Documents in support/documents/ (.md, .txt or .pdf) are split into chunks
and embedded with Chroma's built-in model (all-MiniLM-L6-v2 via ONNX, no
API key needed; it is downloaded on first use). The database lives at
settings.CHROMA_PATH, which on Railway sits on a mounted Volume.

    python manage.py build_knowledge_base            # (re)load the documents
    python manage.py build_knowledge_base --query "how long is the warranty"

Building is repeatable: chunks are upserted with stable IDs, and chunks
from deleted or shortened documents are removed.
"""

import re
from pathlib import Path

from django.conf import settings

DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"
COLLECTION_NAME = "volthub_docs"
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}
MAX_CHUNK_CHARS = 900

_collection = None


def get_collection():
    """The persistent ChromaDB collection (created on first use)."""
    global _collection
    if _collection is None:
        # Imported here: chromadb is heavy and only needed for the knowledge base
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        Path(settings.CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=DefaultEmbeddingFunction(),
            configuration={"hnsw": {"space": "cosine"}},
        )
    return _collection


def read_document(path):
    """Plain text of a .md, .txt or .pdf file."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def document_title(text, path):
    """The first markdown heading, or a title made from the file name."""
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return Path(path).stem.replace("-", " ").replace("_", " ").capitalize()


def chunk_text(text, max_chars=MAX_CHUNK_CHARS):
    """
    Split text into chunks of about max_chars characters.

    Paragraphs are kept whole where possible, a markdown heading always
    starts a new chunk (so sections are not mixed), and very long
    paragraphs are split on sentence boundaries, then on spaces.
    """
    pieces = []
    for block in (b.strip() for b in re.split(r"\n\s*\n", text)):
        if not block:
            continue
        if len(block) <= max_chars:
            pieces.append(block)
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", block):
            while len(sentence) > max_chars:
                cut = sentence.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                pieces.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                pieces.append(sentence)

    chunks = []
    current = ""
    has_body = False  # a chunk that only holds headings keeps growing

    for piece in pieces:
        is_heading = piece.startswith("#")
        too_big = len(current) + len(piece) + 2 > max_chars
        if current and has_body and (is_heading or too_big):
            chunks.append(current)
            current, has_body = piece, not is_heading
        else:
            current = f"{current}\n\n{piece}" if current else piece
            has_body = has_body or not is_heading

    if current:
        chunks.append(current)
    return chunks


def build_knowledge_base(documents_dir=DOCUMENTS_DIR, collection=None):
    """Load every supported document into ChromaDB. Returns a summary."""
    collection = collection or get_collection()
    files = sorted(
        path for path in Path(documents_dir).iterdir()
        if path.suffix.lower() in SUPPORTED_SUFFIXES
    )

    ids, texts, metadatas = [], [], []
    for path in files:
        text = read_document(path)
        title = document_title(text, path)
        for index, chunk in enumerate(chunk_text(text)):
            ids.append(f"{path.name}::{index}")
            # Keep the document title in every chunk so it is found by topic
            texts.append(chunk if chunk.startswith(f"# {title}") else f"{title}\n\n{chunk}")
            metadatas.append({"source": path.name, "title": title, "chunk": index})

    existing = set(collection.get(include=[])["ids"])
    stale = sorted(existing - set(ids))
    if stale:
        collection.delete(ids=stale)
    if ids:
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)

    return {"documents": len(files), "chunks": len(ids), "removed": len(stale)}


def search_knowledge_base(query, n_results=3, collection=None):
    """The chunks most relevant to the query, best match first."""
    collection = collection or get_collection()
    count = collection.count()
    if count == 0:
        return {
            "results": [],
            "note": "The knowledge base is empty. Run: python manage.py build_knowledge_base",
        }

    found = collection.query(query_texts=[query], n_results=min(n_results, count))
    return {
        "results": [
            {
                "source": meta["source"],
                "title": meta["title"],
                "text": text,
                "distance": round(distance, 3),
            }
            for text, meta, distance in zip(
                found["documents"][0], found["metadatas"][0], found["distances"][0]
            )
        ]
    }
