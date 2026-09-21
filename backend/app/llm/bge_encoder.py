"""Pretrained BGE deep encoder served via ONNX Runtime.

Loads the real BAAI bge-small-zh-v1.5 model (4-layer BERT, hidden size 512):

    tokenize (WordPiece) -> ONNX BERT forward -> masked mean pooling
    -> L2 normalization -> 512-d sentence embeddings

Runs fully offline on CPU. The InferenceSession is created lazily and reused;
callers that cannot afford the startup cost use the hash embedder instead.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

MODEL_DIR = Path(__file__).with_name("models").joinpath("bge-small-zh-v1.5")
ONNX_PATH = MODEL_DIR / "model_qint8.onnx"
VOCAB_PATH = MODEL_DIR / "vocab.txt"

BGE_DIM = 512
# BGE v1.5 recommends an instruction prefix for asymmetric (query->passage)
# retrieval; kept here for symmetric short-text matching by default.
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

_session = None
_tokenizer = None


def is_available() -> bool:
    return ONNX_PATH.exists() and VOCAB_PATH.exists()


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from app.llm.wordpiece import WordPieceTokenizer

        _tokenizer = WordPieceTokenizer(VOCAB_PATH)
    return _tokenizer


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.log_severity_level = 3
        _session = ort.InferenceSession(
            str(ONNX_PATH), sess_options=options, providers=["CPUExecutionProvider"]
        )
    return _session


def _encode_batch(texts: Sequence[str], prefix: str = "") -> np.ndarray:
    tokenizer = _get_tokenizer()
    prepared = [f"{prefix}{text}" for text in texts]
    encoded = [tokenizer.encode(text, max_length=128) for text in prepared]
    input_ids = np.asarray([row[0] for row in encoded], dtype=np.int64)
    attention_mask = np.asarray([row[1] for row in encoded], dtype=np.int64)
    token_type_ids = np.asarray([row[2] for row in encoded], dtype=np.int64)

    session = _get_session()
    last_hidden = session.run(
        ["last_hidden_state"],
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )[0]

    mask = attention_mask[:, :, None].astype(np.float64)
    summed = (last_hidden * mask).sum(axis=1)
    counts = np.clip(mask.sum(axis=1), 1e-9, None)
    embeddings = summed / counts
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.clip(norms, 1e-12, None)


def encode_texts(
    texts: Sequence[str],
    batch_size: int = 16,
    is_query: bool = False,
    use_instruction: bool = False,
) -> np.ndarray:
    """Return an L2-normalized [N, 512] embedding matrix."""
    if not texts:
        return np.zeros((0, BGE_DIM), dtype=np.float64)
    prefix = QUERY_INSTRUCTION if (is_query and use_instruction) else ""
    outputs: List[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        outputs.append(_encode_batch(texts[start : start + batch_size], prefix=prefix))
    return np.vstack(outputs)


def encode_text(text: str, is_query: bool = False) -> np.ndarray:
    return encode_texts([text], is_query=is_query)[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b)))


def reset_cache() -> None:
    global _session, _tokenizer
    _session = None
    _tokenizer = None
