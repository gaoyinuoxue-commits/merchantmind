from __future__ import annotations

import numpy as np
import pytest

from app.agent import intent_dnn
from app.agent.intent_ml import classify_with_backend
from app.llm import bge_encoder


# ---------------------------------------------------------------------------
# Pretrained BGE encoder (real downloaded Transformer)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def bge_embeddings():
    if not bge_encoder.is_available():
        pytest.skip("pretrained BGE model files not present")
    texts = [
        "为什么投广告一直在亏钱",
        "广告投产比最近持续下滑",
        "今天天气很好",
    ]
    return texts, bge_encoder.encode_texts(texts)


def test_bge_output_shape_and_normalization(bge_embeddings) -> None:
    _texts, vectors = bge_embeddings
    assert vectors.shape == (3, 512)
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_bge_semantic_beats_unrelated(bge_embeddings) -> None:
    _texts, vectors = bge_embeddings
    same_meaning = float(vectors[0] @ vectors[1])
    unrelated = float(vectors[0] @ vectors[2])
    assert same_meaning > unrelated + 0.15


# ---------------------------------------------------------------------------
# Trainable MLP head (no BERT needed — fast synthetic features)
# ---------------------------------------------------------------------------
def _separable_data(n_per_class: int = 60, seed: int = 3):
    rng = np.random.default_rng(seed)
    centers = np.array([[2.0, 0.0], [0.0, 2.0], [-2.0, -1.0]])
    xs, ys = [], []
    for label, center in enumerate(centers):
        xs.append(rng.normal(center, 0.6, size=(n_per_class, 2)))
        ys.extend([label] * n_per_class)
    return np.vstack(xs), np.asarray(ys)


def test_mlp_head_learns_separable_data() -> None:
    X, y = _separable_data()
    head = intent_dnn.MLPHead(n_features=2, n_hidden=16, n_classes=3, seed=1)
    initial_loss = head.fit(X, y, epochs=1, lr=0.05)[0]
    losses = head.fit(X, y, epochs=120, lr=0.05, dropout=0.0)
    assert losses[-1] < initial_loss
    preds = np.argmax(head.predict_proba(X), axis=1)
    assert (preds == y).mean() > 0.95


def test_mlp_head_seed_init_is_deterministic() -> None:
    a = intent_dnn.MLPHead(8, 5, 3, seed=42)
    b = intent_dnn.MLPHead(8, 5, 3, seed=42)
    assert np.allclose(a.W1, b.W1) and np.allclose(a.W2, b.W2)


# ---------------------------------------------------------------------------
# Artifact persistence + backend routing
# ---------------------------------------------------------------------------
def test_deep_model_save_load_roundtrip(tmp_path) -> None:
    head = intent_dnn.MLPHead(8, 5, 3, seed=5)
    model = intent_dnn.DeepIntentModel(head, ["a", "b", "c"])
    path = tmp_path / "dnn.npz"
    model.save(path)

    loaded = intent_dnn.load_deep_model(path)
    assert loaded is not None and loaded.labels == ["a", "b", "c"]
    assert np.allclose(loaded.head.W1, head.W1)
    assert np.allclose(loaded.head.W2, head.W2)


def test_load_missing_artifact_returns_none(tmp_path) -> None:
    assert intent_dnn.load_deep_model(tmp_path / "nope.npz") is None


def test_dnn_backend_routes_to_trained_model() -> None:
    if intent_dnn.load_deep_model() is None:
        pytest.skip("trained deep intent artifact not present")
    intent_dnn.reset_deep_cache()
    result = classify_with_backend("为什么最近ROI一直下滑", backend="dnn")
    assert result.intent == "performance_diagnosis"
    assert result.confidence > 0.8
