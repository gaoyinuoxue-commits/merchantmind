"""A real, trainable intent classifier — multinomial logistic regression.

This module contains an actual supervised model (no pretrained download):

- Features: Latin words + CJK character bigrams (reusing the offline tokenizer)
  encoded as TF-IDF over a learned vocabulary.
- Model: softmax multinomial logistic regression trained with mini-batch
  gradient descent (cross-entropy + L2), implemented from scratch in numpy.
- Artifacts: ``intent_weights.npz`` (W / b / idf) + ``intent_vocab.json``
  (vocabulary, label order, training meta), living next to this module so the
  backend Docker image ships them with ``COPY app``.

If the artifacts are missing or unreadable the classifier degrades to the
deterministic rule classifier, so the API never breaks on a fresh checkout
until ``scripts/train_intent_model.py`` is run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.agent.intent import (
    IntentResult,
    classify_intent,
    extract_signals,
)
from app.agent.intent_dataset import LABELS
from app.config.settings import get_settings
from app.llm.embeddings import tokenize as _base_tokenize

_CJK_CHARS = re.compile(r"[\u4e00-\u9fff]")


def intent_tokenize(text: str) -> List[str]:
    """Intent features use bigrams (shared tokenizer) PLUS CJK unigrams.

    Single-character tokens are essential for very short utterances such as
    greetings ("在么" vs the seen "在吗") that otherwise hash to an almost
    empty vector; common characters get naturally down-weighted by idf.
    """
    tokens = _base_tokenize(text)
    tokens.extend(_CJK_CHARS.findall(text))
    return tokens

WEIGHTS_PATH = Path(__file__).with_name("intent_weights.npz")
VOCAB_PATH = Path(__file__).with_name("intent_vocab.json")

# An ML prediction only overrides the rule classifier in hybrid mode when the
# model is at least this confident (softmax probability scales 0..1).
HYBRID_TRUST_THRESHOLD = 0.60


class TfidfVectorizer:
    """Vocabulary + smoothed idf learned from training tokens."""

    def __init__(self, min_df: int = 2, max_features: int = 4000) -> None:
        self.min_df = min_df
        self.max_features = max_features
        self.vocab: Dict[str, int] = {}
        self.idf: np.ndarray = np.zeros(0)

    def fit(self, token_rows: Sequence[Sequence[str]]) -> "TfidfVectorizer":
        n_docs = len(token_rows)
        document_frequency: Dict[str, int] = {}
        for tokens in token_rows:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        eligible = [
            (token, df) for token, df in document_frequency.items() if df >= self.min_df
        ]
        eligible.sort(key=lambda row: (-row[1], row[0]))
        eligible = eligible[: self.max_features]
        self.vocab = {token: idx for idx, (token, _df) in enumerate(eligible)}
        idf = np.empty(len(self.vocab), dtype=np.float64)
        for token, idx in self.vocab.items():
            df = document_frequency[token]
            idf[idx] = np.log((n_docs + 1.0) / (df + 1.0)) + 1.0
        self.idf = idf
        return self

    def transform(self, token_rows: Sequence[Sequence[str]]) -> np.ndarray:
        rows = np.zeros((len(token_rows), len(self.vocab)), dtype=np.float64)
        for row_idx, tokens in enumerate(token_rows):
            counts: Dict[int, float] = {}
            for token in tokens:
                col = self.vocab.get(token)
                if col is not None:
                    counts[col] = counts.get(col, 0.0) + 1.0
            for col, tf in counts.items():
                rows[row_idx, col] = tf * self.idf[col]
            norm = np.linalg.norm(rows[row_idx])
            if norm > 0:
                rows[row_idx] /= norm
        return rows

    def to_meta(self) -> Dict[str, Any]:
        return {"vocab": self.vocab, "idf": self.idf.tolist()}

    @classmethod
    def from_meta(cls, vocab: Dict[str, int], idf: Sequence[float]) -> "TfidfVectorizer":
        vectorizer = cls()
        vectorizer.vocab = dict(vocab)
        vectorizer.idf = np.asarray(idf, dtype=np.float64)
        return vectorizer


class SoftmaxRegression:
    """Softmax multinomial logistic regression trained with SGD."""

    def __init__(self, n_features: int, n_classes: int) -> None:
        self.n_features = n_features
        self.n_classes = n_classes
        self.W = np.zeros((n_features, n_classes), dtype=np.float64)
        self.b = np.zeros(n_classes, dtype=np.float64)

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=1, keepdims=True)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 300,
        batch_size: int = 32,
        lr: float = 0.5,
        l2: float = 1e-4,
        seed: int = 20260915,
        sample_weight: Optional[np.ndarray] = None,
    ) -> List[float]:
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0.0, 0.01, size=self.W.shape)
        self.b = np.zeros(self.n_classes, dtype=np.float64)
        n = X.shape[0]
        if sample_weight is None:
            sample_weight = np.ones(n, dtype=np.float64)
        y_onehot = np.zeros((n, self.n_classes), dtype=np.float64)
        y_onehot[np.arange(n), y] = 1.0
        losses: List[float] = []
        for _epoch in range(epochs):
            order = rng.permutation(n)
            for start in range(0, n, batch_size):
                idx = order[start : start + batch_size]
                xb, yb = X[idx], y_onehot[idx]
                sw = sample_weight[idx]
                denom = float(sw.sum()) or 1.0
                probs = self._softmax(xb @ self.W + self.b)
                error = (probs - yb) * sw[:, None]
                grad_w = (xb.T @ error) / denom + l2 * self.W
                grad_b = error.sum(axis=0) / denom
                self.W -= lr * grad_w
                self.b -= lr * grad_b
            probs = self._softmax(X @ self.W + self.b)
            loss = float(
                -np.mean(np.log(probs[np.arange(n), y] + 1e-12))
                + 0.5 * l2 * float(np.mean(self.W ** 2))
            )
            losses.append(loss)
        return losses

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._softmax(X @ self.W + self.b)


class TrainedIntentModel:
    def __init__(
        self,
        vectorizer: TfidfVectorizer,
        clf: SoftmaxRegression,
        labels: List[str],
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.vectorizer = vectorizer
        self.clf = clf
        self.labels = labels
        self.meta = meta or {}

    def predict_text(self, text: str) -> Tuple[str, float, np.ndarray]:
        X = self.vectorizer.transform([intent_tokenize(text)])
        probs = self.clf.predict_proba(X)[0]
        idx = int(np.argmax(probs))
        return self.labels[idx], float(probs[idx]), probs

    def save(self, weights_path: Path = WEIGHTS_PATH, vocab_path: Path = VOCAB_PATH) -> None:
        np.savez(weights_path, W=self.clf.W, b=self.clf.b)
        payload = {
            "vocab": self.vectorizer.vocab,
            "idf": self.vectorizer.idf.tolist(),
            "labels": self.labels,
            "meta": self.meta,
        }
        vocab_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def train_model(
    texts: Sequence[str],
    labels: Sequence[int],
    labels_order: Sequence[str] = LABELS,
    hyperparams: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> TrainedIntentModel:
    hyperparams = hyperparams or {}
    tokens = [intent_tokenize(text) for text in texts]
    vectorizer = TfidfVectorizer(
        min_df=int(hyperparams.get("min_df", 2)),
        max_features=int(hyperparams.get("max_features", 4000)),
    ).fit(tokens)
    X = vectorizer.transform(tokens)
    y = np.asarray(labels, dtype=np.int64)

    # Balanced class weights: N / (C * count_c). Greetings are far rarer than
    # augmented diagnostic utterances and would otherwise be under-learned.
    n_classes = len(labels_order)
    counts = np.bincount(y, minlength=n_classes).astype(np.float64)
    class_weight = np.full(n_classes, 1.0, dtype=np.float64)
    present = counts > 0
    class_weight[present] = len(y) / (n_classes * counts[present])
    sample_weight = class_weight[y]

    clf = SoftmaxRegression(n_features=X.shape[1], n_classes=n_classes)
    clf.fit(
        X,
        y,
        epochs=int(hyperparams.get("epochs", 300)),
        batch_size=int(hyperparams.get("batch_size", 32)),
        lr=float(hyperparams.get("lr", 0.5)),
        l2=float(hyperparams.get("l2", 1e-4)),
        seed=int(hyperparams.get("seed", 20260915)),
        sample_weight=sample_weight,
    )
    return TrainedIntentModel(vectorizer, clf, list(labels_order), meta=meta)


def load_model(
    weights_path: Path = WEIGHTS_PATH, vocab_path: Path = VOCAB_PATH
) -> Optional[TrainedIntentModel]:
    if not weights_path.exists() or not vocab_path.exists():
        return None
    try:
        payload = json.loads(vocab_path.read_text(encoding="utf-8"))
        with np.load(weights_path) as data:
            W, b = data["W"], data["b"]
        vectorizer = TfidfVectorizer.from_meta(payload["vocab"], payload["idf"])
        clf = SoftmaxRegression(n_features=W.shape[0], n_classes=W.shape[1])
        clf.W, clf.b = W, b
        return TrainedIntentModel(vectorizer, clf, payload["labels"], meta=payload.get("meta", {}))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


_model_cache: Optional[TrainedIntentModel] = None
_model_loaded = False


def get_model() -> Optional[TrainedIntentModel]:
    global _model_cache, _model_loaded
    if not _model_loaded:
        _model_cache = load_model()
        _model_loaded = True
    return _model_cache


def reset_model_cache() -> None:
    global _model_cache, _model_loaded
    _model_cache = None
    _model_loaded = False


def classify_intent_ml(text: str) -> Optional[IntentResult]:
    """Classify with the trained model; return None when unavailable."""
    model = get_model()
    if model is None:
        return None
    intent, confidence, _probs = model.predict_text(text)
    signals = extract_signals(text)
    signals["matched"] = []
    return IntentResult(intent=intent, confidence=round(confidence, 4), signals=signals)


def classify_with_backend(text: str, backend: Optional[str] = None) -> IntentResult:
    """Single intent entry point: rule | ml | dnn | hybrid.

    - rule: deterministic keyword classifier (default, stable for evaluation)
    - ml: trained softmax classifier, falling back to rule if no artifact
    - dnn: pretrained BGE(BERT) encoder + trained MLP head, fallback to rule
    - hybrid: use ml only when its probability clears HYBRID_TRUST_THRESHOLD
    """
    backend = (backend or get_settings().intent_classifier_backend or "rule").lower()
    if backend == "dnn":
        from app.agent.intent_dnn import classify_intent_dnn

        dnn_result = classify_intent_dnn(text)
        return dnn_result if dnn_result is not None else classify_intent(text)
    if backend == "ml":
        ml_result = classify_intent_ml(text)
        return ml_result if ml_result is not None else classify_intent(text)
    if backend == "hybrid":
        rule_result = classify_intent(text)
        ml_result = classify_intent_ml(text)
        if ml_result is not None and ml_result.confidence >= HYBRID_TRUST_THRESHOLD:
            return ml_result
        return rule_result
    return classify_intent(text)
