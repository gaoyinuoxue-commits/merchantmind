"""Deep intent classifier via transfer learning on a pretrained BERT model.

Pipeline:

    text -> frozen pretrained BAAI bge-small-zh-v1.5 (4-layer BERT)
          -> 512-d sentence embedding
          -> trainable MLP head: 512 -> 128 (ReLU + Dropout) -> n classes
          -> softmax

The encoder weights are *frozen* (no backprop through the Transformer); only
the MLP head is trained, from scratch, with numpy mini-batch gradient descent
(cross-entropy + balanced class weights + L2). This mirrors the standard
"pretrained encoder + classification head" fine-tuning pattern while staying
fully offline and CPU-only.

Artifact: ``intent_dnn_weights.npz`` next to this module; if missing the
caller degrades to the rule classifier.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.agent.intent import IntentResult, extract_signals
from app.agent.intent_dataset import LABELS

WEIGHTS_PATH = Path(__file__).with_name("intent_dnn_weights.npz")
HIDDEN_SIZE = 128
DROPOUT = 0.20


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class MLPHead:
    """Two-layer MLP (one hidden ReLU layer + softmax), numpy backprop."""

    def __init__(self, n_features: int, n_hidden: int, n_classes: int, seed: int = 7):
        rng = np.random.default_rng(seed)
        # He initialization for the ReLU layer.
        self.W1 = rng.normal(0.0, np.sqrt(2.0 / n_features), size=(n_features, n_hidden))
        self.b1 = np.zeros(n_hidden)
        self.W2 = rng.normal(0.0, np.sqrt(1.0 / n_hidden), size=(n_hidden, n_classes))
        self.b2 = np.zeros(n_classes)
        self.n_classes = n_classes

    def forward(
        self, X: np.ndarray, dropout: float = 0.0, rng: Optional[np.random.Generator] = None
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        z1 = X @ self.W1 + self.b1
        a1 = _relu(z1)
        mask = np.ones_like(a1)
        if dropout > 0.0 and rng is not None:
            keep = 1.0 - dropout
            mask = (rng.random(a1.shape) < keep).astype(np.float64) / keep
            a1 = a1 * mask
        logits = a1 @ self.W2 + self.b2
        probs = _softmax(logits)
        cache = {"X": X, "z1": z1, "a1": a1, "mask": mask}
        return probs, cache

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 250,
        batch_size: int = 32,
        lr: float = 0.08,
        l2: float = 1e-4,
        dropout: float = DROPOUT,
        sample_weight: Optional[np.ndarray] = None,
        seed: int = 20260919,
    ) -> List[float]:
        rng = np.random.default_rng(seed)
        n = X.shape[0]
        if sample_weight is None:
            sample_weight = np.ones(n)
        y_onehot = np.zeros((n, self.n_classes))
        y_onehot[np.arange(n), y] = 1.0
        losses: List[float] = []
        for _epoch in range(epochs):
            order = rng.permutation(n)
            for start in range(0, n, batch_size):
                idx = order[start : start + batch_size]
                xb, yb = X[idx], y_onehot[idx]
                sw = sample_weight[idx][:, None]
                denom = float(sw.sum()) or 1.0
                probs, cache = self.forward(xb, dropout=dropout, rng=rng)

                dz2 = (probs - yb) * sw
                grad_w2 = (cache["a1"].T @ dz2) / denom + l2 * self.W2
                grad_b2 = dz2.sum(axis=0) / denom

                da1 = dz2 @ self.W2.T
                da1 = da1 * cache["mask"]
                da1[cache["z1"] <= 0] = 0
                grad_w1 = (xb.T @ da1) / denom + l2 * self.W1
                grad_b1 = da1.sum(axis=0) / denom

                self.W2 -= lr * grad_w2
                self.b2 -= lr * grad_b2
                self.W1 -= lr * grad_w1
                self.b1 -= lr * grad_b1

            probs, _ = self.forward(X)
            loss = float(
                -np.sum(sample_weight * np.log(probs[np.arange(n), y] + 1e-12)) / n
                + 0.5 * l2 * (float(np.mean(self.W1 ** 2)) + float(np.mean(self.W2 ** 2)))
            )
            losses.append(loss)
        return losses

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs, _ = self.forward(X)
        return probs


class DeepIntentModel:
    def __init__(self, head: MLPHead, labels: List[str], meta: Optional[Dict[str, Any]] = None):
        self.head = head
        self.labels = labels
        self.meta = meta or {}

    def _features(self, texts: Sequence[str]) -> np.ndarray:
        from app.llm.bge_encoder import encode_texts

        return np.asarray(encode_texts(list(texts)), dtype=np.float64)

    def predict_text(self, text: str) -> Tuple[str, float, np.ndarray]:
        probs = self.head.predict_proba(self._features([text]))[0]
        idx = int(np.argmax(probs))
        return self.labels[idx], float(probs[idx]), probs

    def save(self, path: Path = WEIGHTS_PATH) -> None:
        np.savez(
            path,
            W1=self.head.W1,
            b1=self.head.b1,
            W2=self.head.W2,
            b2=self.head.b2,
            labels=np.asarray(self.labels),
        )


def train_deep_model(
    texts: Sequence[str],
    labels: Sequence[int],
    labels_order: Sequence[str] = LABELS,
    hyperparams: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> DeepIntentModel:
    hyperparams = hyperparams or {}
    from app.llm.bge_encoder import encode_texts

    X = np.asarray(encode_texts(list(texts)), dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    n_classes = len(labels_order)

    counts = np.bincount(y, minlength=n_classes).astype(np.float64)
    class_weight = np.full(n_classes, 1.0)
    present = counts > 0
    class_weight[present] = len(y) / (n_classes * counts[present])

    head = MLPHead(X.shape[1], HIDDEN_SIZE, n_classes, seed=7)
    head.fit(
        X,
        y,
        epochs=int(hyperparams.get("epochs", 250)),
        batch_size=int(hyperparams.get("batch_size", 32)),
        lr=float(hyperparams.get("lr", 0.08)),
        l2=float(hyperparams.get("l2", 1e-4)),
        dropout=float(hyperparams.get("dropout", DROPOUT)),
        sample_weight=class_weight[y],
        seed=int(hyperparams.get("seed", 20260919)),
    )
    return DeepIntentModel(head, list(labels_order), meta=meta)


def load_deep_model(path: Path = WEIGHTS_PATH) -> Optional[DeepIntentModel]:
    if not path.exists():
        return None
    try:
        with np.load(path) as data:
            labels = [str(item) for item in data["labels"]]
            head = MLPHead(
                n_features=data["W1"].shape[0],
                n_hidden=data["W1"].shape[1],
                n_classes=data["W2"].shape[1],
            )
            head.W1, head.b1 = data["W1"], data["b1"]
            head.W2, head.b2 = data["W2"], data["b2"]
        return DeepIntentModel(head, labels)
    except (OSError, ValueError, KeyError):
        return None


_dnn_cache: Optional[DeepIntentModel] = None
_dnn_loaded = False


def get_deep_model() -> Optional[DeepIntentModel]:
    global _dnn_cache, _dnn_loaded
    if not _dnn_loaded:
        _dnn_cache = load_deep_model()
        _dnn_loaded = True
    return _dnn_cache


def reset_deep_cache() -> None:
    global _dnn_cache, _dnn_loaded
    _dnn_cache = None
    _dnn_loaded = False


def classify_intent_dnn(text: str) -> Optional[IntentResult]:
    """Classify with the pretrained-BERT + MLP model; None when unavailable."""
    model = get_deep_model()
    if model is None:
        return None
    intent, confidence, _probs = model.predict_text(text)
    signals = extract_signals(text)
    signals["matched"] = []
    return IntentResult(intent=intent, confidence=round(confidence, 4), signals=signals)
