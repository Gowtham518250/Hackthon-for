import os
from pathlib import Path
from threading import RLock

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

MODEL_REPO = os.getenv("EMBEDDING_MODEL_REPO", "Xenova/all-MiniLM-L6-v2")

requested_cache = os.getenv(
    "HF_HOME",
    str(Path("/tmp") / ".cache" / "huggingface"),
)
MODEL_CACHE = Path(requested_cache)
if not MODEL_CACHE.is_absolute() or str(MODEL_CACHE).startswith("/app"):
    MODEL_CACHE = Path("/tmp") / ".cache" / "huggingface"

MODEL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(MODEL_CACHE)
os.environ["HF_XET_CACHE"] = str(MODEL_CACHE / "xet")
os.environ["HF_HUB_CACHE"] = str(MODEL_CACHE / "hub")
os.environ["HF_HUB_DISABLE_XET"] = "1"

_LOCK = RLock()
_TOKENIZER: Tokenizer | None = None
_SESSION: ort.InferenceSession | None = None
_INPUT_NAMES: set[str] = set()


def _ensure_model() -> tuple[Tokenizer, ort.InferenceSession, set[str]]:
    global _TOKENIZER, _SESSION, _INPUT_NAMES

    if _TOKENIZER is not None and _SESSION is not None:
        return _TOKENIZER, _SESSION, _INPUT_NAMES

    with _LOCK:
        if _TOKENIZER is not None and _SESSION is not None:
            return _TOKENIZER, _SESSION, _INPUT_NAMES

        tokenizer_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename="tokenizer.json",
            cache_dir=str(MODEL_CACHE),
        )
        model_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename="onnx/model.onnx",
            cache_dir=str(MODEL_CACHE),
        )

        tokenizer = Tokenizer.from_file(tokenizer_path)
        tokenizer.enable_truncation(max_length=256)
        session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )

        _TOKENIZER = tokenizer
        _SESSION = session
        _INPUT_NAMES = {item.name for item in session.get_inputs()}

    return _TOKENIZER, _SESSION, _INPUT_NAMES


def _embed(text: str) -> list[float]:
    tokenizer, session, input_names = _ensure_model()

    encoded = tokenizer.encode(text)
    attention_mask = np.asarray([encoded.attention_mask], dtype=np.int64)
    inputs = {
        "input_ids": np.asarray([encoded.ids], dtype=np.int64),
        "attention_mask": attention_mask,
    }

    if "token_type_ids" in input_names:
        inputs["token_type_ids"] = np.asarray(
            [encoded.type_ids],
            dtype=np.int64,
        )

    outputs = session.run(None, inputs)
    token_embeddings = outputs[0]

    mask = attention_mask[..., None].astype(np.float32)
    pooled = (token_embeddings * mask).sum(axis=1) / np.clip(
        mask.sum(axis=1),
        1e-9,
        None,
    )

    norm = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / np.clip(norm, 1e-12, None)

    return pooled[0].astype(np.float32).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [_embed(text) for text in texts]


def embed_query(text: str) -> list[float]:
    return _embed(text)


def embedding_status() -> dict:
    return {
        "model": MODEL_REPO,
        "loaded": _TOKENIZER is not None and _SESSION is not None,
        "cache_dir": str(MODEL_CACHE),
    }
