import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

MODEL_REPO = os.getenv("EMBEDDING_MODEL_REPO", "Xenova/all-MiniLM-L6-v2")
# Render Free instances have a writable /tmp but the application directory
# can be read-only. Always use an explicit writable cache unless a custom
# cache path is both absolute and outside /app.
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

TOKENIZER_PATH = hf_hub_download(
    repo_id=MODEL_REPO,
    filename="tokenizer.json",
    cache_dir=str(MODEL_CACHE),
)
MODEL_PATH = hf_hub_download(
    repo_id=MODEL_REPO,
    filename="onnx/model.onnx",
    cache_dir=str(MODEL_CACHE),
)

_TOKENIZER = Tokenizer.from_file(TOKENIZER_PATH)
_TOKENIZER.enable_truncation(max_length=256)
_SESSION = ort.InferenceSession(
    MODEL_PATH,
    providers=["CPUExecutionProvider"],
)
_INPUT_NAMES = {item.name for item in _SESSION.get_inputs()}


def _embed(text: str) -> list[float]:
    encoded = _TOKENIZER.encode(text)
    attention_mask = np.asarray([encoded.attention_mask], dtype=np.int64)
    inputs = {
        "input_ids": np.asarray([encoded.ids], dtype=np.int64),
        "attention_mask": attention_mask,
    }

    if "token_type_ids" in _INPUT_NAMES:
        inputs["token_type_ids"] = np.asarray(
            [encoded.type_ids],
            dtype=np.int64,
        )

    outputs = _SESSION.run(None, inputs)
    token_embeddings = outputs[0]

    mask = attention_mask[..., None].astype(np.float32)
    pooled = (token_embeddings * mask).sum(axis=1) / np.clip(
        mask.sum(axis=1),
        1e-9,
        None,
    )

    # Same normalized all-MiniLM-L6-v2 representation used by Retail Mind.
    norm = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / np.clip(norm, 1e-12, None)
    return pooled[0].astype(np.float32).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [_embed(text) for text in texts]


def embed_query(text: str) -> list[float]:
    return _embed(text)
