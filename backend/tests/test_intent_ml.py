"""Tests for the trainable intent classifier and its rule/ml/hybrid routing.

Pure unit tests (no database): dataset hygiene, model learning, determinism,
artifact round-trip, pretrained predictions and graceful rule fallback.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.agent import intent_ml
from app.agent.intent import classify_intent
from app.agent.intent_dataset import (
    LABELS,
    HANDWRITTEN,
    build_dataset,
    expansions,
)
from app.agent.intent_ml import (
    VOCAB_PATH,
    WEIGHTS_PATH,
    classify_with_backend,
    intent_tokenize,
    load_model,
    reset_model_cache,
    train_model,
)


@pytest.fixture()
def clean_model_cache():
    reset_model_cache()
    yield
    reset_model_cache()


def test_dataset_is_labelled_stratified_and_leak_free():
    train_texts, train_labels, test_texts, test_labels = build_dataset()
    assert set(LABELS) == {
        "performance_diagnosis",
        "strategy_consultation",
        "action_request",
        "knowledge_query",
        "greeting",
    }
    assert set(test_labels) == set(range(len(LABELS)))
    assert len(test_texts) == len(test_labels)
    assert len(train_texts) == len(train_labels)
    # Held-out hand-written sentences must not appear verbatim in train.
    assert set(test_texts).isdisjoint(set(train_texts))
    # Augmentation exists and is only fed to training.
    assert sum(len(rows) for rows in expansions().values()) > 100


def test_intent_tokenizer_keeps_latin_and_cjk_unigrams():
    tokens = intent_tokenize("ROI 在么")
    assert "roi" in tokens
    assert "在" in tokens and "么" in tokens
    assert "在么" in tokens


def test_model_learns_separable_data_and_predicts_valid_distribution():
    texts, labels = [], []
    for label_id, label in enumerate(LABELS):
        for sentence in HANDWRITTEN[label][:8]:
            texts.append(sentence)
            labels.append(label_id)
    model = train_model(texts, labels, hyperparams={"epochs": 250})
    X = model.vectorizer.transform([intent_tokenize(text) for text in texts])
    pred = np.argmax(model.clf.predict_proba(X), axis=1)
    assert (pred == np.asarray(labels)).mean() >= 0.85
    label, confidence, probs = model.predict_text("为什么 ROI 一直下降")
    assert label in LABELS
    assert 0.0 <= confidence <= 1.0
    assert abs(float(probs.sum()) - 1.0) < 1e-6


def test_training_is_deterministic_under_fixed_seed():
    texts = ["ROI 下降", "你好", "帮我关计划", "ROI 是什么", "怎么优化"]
    labels = [0, 4, 2, 3, 1]
    first = train_model(texts * 4, labels * 4, hyperparams={"epochs": 50})
    second = train_model(texts * 4, labels * 4, hyperparams={"epochs": 50})
    assert np.allclose(first.clf.W, second.clf.W)
    assert np.allclose(first.clf.b, second.clf.b)


def test_save_load_roundtrip_matches_predictions(tmp_path):
    weights = tmp_path / "weights.npz"
    vocab = tmp_path / "vocab.json"
    texts, labels = [], []
    for label_id, label in enumerate(LABELS):
        for sentence in HANDWRITTEN[label][:6]:
            texts.append(sentence)
            labels.append(label_id)
    model = train_model(texts, labels, hyperparams={"epochs": 120})
    model.save(weights, vocab)
    loaded = load_model(weights, vocab)
    assert loaded is not None
    for sentence in ["为什么点击率掉了", "你好", "帮我暂停计划", "CPM 怎么算", "怎么提升 ROI"]:
        label_a, conf_a, probs_a = model.predict_text(sentence)
        label_b, conf_b, probs_b = loaded.predict_text(sentence)
        assert label_a == label_b
        assert conf_a == conf_b
        assert np.allclose(probs_a, probs_b)


def test_ml_backend_falls_back_to_rule_without_artifact(monkeypatch):
    monkeypatch.setattr(intent_ml, "get_model", lambda: None)
    query = "为什么最近 ROI 一直下降"
    result = classify_with_backend(query, "ml")
    assert result.intent == classify_intent(query).intent
    assert intent_ml.classify_intent_ml("anything") is None


@pytest.mark.skipif(
    not (WEIGHTS_PATH.exists() and VOCAB_PATH.exists()),
    reason="intent model artifacts not trained; run scripts/train_intent_model.py",
)
def test_pretrained_ml_classifies_core_intents(clean_model_cache):
    cases = [
        ("为什么最近 ROI 一直下降", "performance_diagnosis"),
        ("你好，在吗", "greeting"),
        ("帮我把这个计划暂停掉", "action_request"),
        ("ROI 是什么意思", "knowledge_query"),
        ("新品怎么推广比较好", "strategy_consultation"),
    ]
    for query, expected in cases:
        assert classify_with_backend(query, "ml").intent == expected, query


@pytest.mark.skipif(
    not (WEIGHTS_PATH.exists() and VOCAB_PATH.exists()),
    reason="intent model artifacts not trained; run scripts/train_intent_model.py",
)
def test_pretrained_ml_preserves_planner_signals(clean_model_cache):
    result = classify_with_backend("为什么 ROI 和点击率都在下降", "ml")
    assert set(result.signals) == {"metrics", "domains", "matched"}
    assert "roi" in result.signals["metrics"]


@pytest.mark.skipif(
    not (WEIGHTS_PATH.exists() and VOCAB_PATH.exists()),
    reason="intent model artifacts not trained; run scripts/train_intent_model.py",
)
def test_rule_is_default_and_hybrid_trusts_confident_ml(clean_model_cache):
    # Default backend stays the deterministic rule classifier.
    assert classify_with_backend("你好").intent == classify_intent("你好").intent
    # Confident short greeting is accepted from ML in hybrid mode.
    assert classify_with_backend("你好呀", "hybrid").intent == "greeting"
