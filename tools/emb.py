from typing import List

from google import genai
from google.genai.types import EmbedContentConfig
import dotenv
import os


dotenv.load_dotenv()

_EMBED_CLIENT: genai.Client | None = None


def _get_embed_client() -> genai.Client:
    """
    Lazily construct a reusable genai.Client for embeddings.

    Requires the following env vars (already used in your example script):
    - GOOGLE_GENAI_USE_VERTEXAI
    - GOOGLE_GENAI_PROJECT
    - GOOGLE_GENAI_LOCATION
    """
    global _EMBED_CLIENT
    if _EMBED_CLIENT is None:
        _EMBED_CLIENT = genai.Client(
            vertexai=os.getenv("GOOGLE_GENAI_USE_VERTEXAI"),
            project=os.getenv("GOOGLE_GENAI_PROJECT"),
            location=os.getenv("GOOGLE_GENAI_LOCATION"),
        )
    return _EMBED_CLIENT


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts using Gemini embeddings.

    Returns a list of embedding vectors (list[float]), one per input text.
    """
    if not texts:
        return []

    client = _get_embed_client()
    vectors: List[List[float]] = []

    # Gemini embedding API has a limit on number of instances per request
    # (e.g., 2048). To be safe and future-proof, we batch the inputs.
    max_batch_size = 200
    for i in range(0, len(texts), max_batch_size):
        chunk = texts[i : i + max_batch_size]
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=chunk,
            config=EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        vectors.extend([emb.values for emb in response.embeddings])

    return vectors


def embed_text(text: str) -> List[float]:
    """
    Convenience wrapper to embed a single text.
    """
    vectors = embed_texts([text])
    return vectors[0] if vectors else []

