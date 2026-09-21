"""Train the intent classifier and write its weight artifacts.

Run from backend/ (PYTHONPATH includes the repo root when started as a file):

    python scripts/train_intent_model.py [--epochs 300] [--no-save]

Outputs dataset stats, training loss, test accuracy of the trained softmax
model versus the deterministic rule classifier on the SAME held-out
hand-written test set, per-class precision/recall/F1 and a confusion matrix,
then writes app/agent/intent_weights.npz + app/agent/intent_vocab.json.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.intent import classify_intent  # noqa: E402
from app.agent.intent_dataset import LABELS, build_dataset  # noqa: E402
from app.agent.intent_ml import (  # noqa: E402
    VOCAB_PATH,
    WEIGHTS_PATH,
    intent_tokenize,
    train_model,
)

SEED = 20260915


def accuracy(y_true: List[int], y_pred: List[int]) -> float:
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / max(1, len(y_true))


def confusion(y_true: List[int], y_pred: List[int], n_classes: int) -> np.ndarray:
    matrix = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        matrix[t, p] += 1
    return matrix


def per_class_prf(matrix: np.ndarray) -> List[Dict[str, float]]:
    rows = []
    for i in range(matrix.shape[0]):
        tp = float(matrix[i, i])
        fp = float(matrix[:, i].sum() - tp)
        fn = float(matrix[i, :].sum() - tp)
        support = float(matrix[i, :].sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        rows.append(
            {"precision": precision, "recall": recall, "f1": f1, "support": support}
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--lr", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument(
        "--backend",
        choices=["ml", "dnn"],
        default="ml",
        help="ml=TF-IDF softmax regression; dnn=frozen pretrained BGE(BERT)+MLP head",
    )
    args = parser.parse_args()

    train_texts, train_labels, test_texts, test_labels = build_dataset(seed=SEED)

    print("=" * 72)
    print("MerchantMind intent classifier — multinomial logistic regression")
    print("features: latin words + CJK bigrams/unigrams, TF-IDF | SGD + balanced class weights")
    print("=" * 72)
    print(f"train rows: {len(train_texts)}   test rows (hand-written): {len(test_texts)}")
    train_dist = Counter(LABELS[i] for i in train_labels)
    test_dist = Counter(LABELS[i] for i in test_labels)
    for label in LABELS:
        print(f"  {label:24s} train={train_dist.get(label, 0):4d}  test={test_dist.get(label, 0):3d}")

    hyperparams = {
        "epochs": args.epochs,
        "lr": args.lr,
        "batch_size": args.batch_size,
        "l2": args.l2,
        "min_df": 2,
        "seed": SEED,
        "class_weighting": "balanced",
    }

    if args.backend == "dnn":
        from app.agent.intent_dnn import (
            WEIGHTS_PATH as DNN_WEIGHTS_PATH,
            train_deep_model,
        )

        print("\n[backend=dnn] frozen pretrained BAAI bge-small-zh-v1.5 (BERT) + MLP head")
        deep = train_deep_model(
            train_texts, train_labels, labels_order=LABELS, hyperparams=hyperparams
        )
        test_features = deep._features(test_texts)
        ml_pred = [int(i) for i in np.argmax(deep.head.predict_proba(test_features), axis=1)]
    else:
        model = train_model(
            train_texts,
            train_labels,
            labels_order=LABELS,
            hyperparams=hyperparams,
        )
        vocab_size = len(model.vectorizer.vocab)
        print(f"\nvocabulary size: {vocab_size}")

        # ML predictions on held-out hand-written test set.
        X_test = model.vectorizer.transform(
            [intent_tokenize(text) for text in test_texts]
        )
        ml_pred = [int(i) for i in np.argmax(model.clf.predict_proba(X_test), axis=1)]

    ml_acc = accuracy(test_labels, ml_pred)

    # Rule baseline on exactly the same test set.
    rule_pred = [LABELS.index(classify_intent(text).intent) for text in test_texts]
    rule_acc = accuracy(test_labels, rule_pred)

    print(f"\ntest accuracy   trained ML model : {ml_acc:.4f}")
    print(f"test accuracy   rule baseline     : {rule_acc:.4f}")

    matrix = confusion(test_labels, ml_pred, len(LABELS))
    print("\nper-class metrics (trained ML):")
    print(f"  {'label':24s} {'precision':>9s} {'recall':>8s} {'f1':>7s} {'support':>8s}")
    for label, stats in zip(LABELS, per_class_prf(matrix)):
        print(
            f"  {label:24s} {stats['precision']:9.3f} {stats['recall']:8.3f} "
            f"{stats['f1']:7.3f} {int(stats['support']):8d}"
        )

    print("\nconfusion matrix (rows=true, cols=pred)")
    short = ["diag", "strat", "action", "know", "hello"]
    header = "true \\ pred   " + " ".join(f"{s:>7s}" for s in short)
    print(header)
    for i, label in enumerate(LABELS):
        print(f"{short[i]:>11s}  " + " ".join(f"{int(v):7d}" for v in matrix[i]))

    errors = [
        (text, LABELS[true], LABELS[pred])
        for text, true, pred in zip(test_texts, test_labels, ml_pred)
        if true != pred
    ]
    if errors:
        print("\nmisclassified hand-written cases:")
        for text, true, pred in errors:
            print(f"  [{true} -> {pred}] {text}")

    if args.no_save:
        print("\n--no-save given; artifacts not written.")
        return 0

    if args.backend == "dnn":
        deep.save(DNN_WEIGHTS_PATH)
        print(f"\nsaved weights : {DNN_WEIGHTS_PATH}")
        print("enable with   : INTENT_CLASSIFIER_BACKEND=dnn (rule|ml|dnn|hybrid)")
    else:
        model.meta = {
            "model": "softmax_multinomial_logistic_regression",
            "features": "latin_words_and_cjk_bigram_unigram_tfidf",
            "seed": SEED,
            "hyperparams": hyperparams,
            "train_rows": len(train_texts),
            "test_rows": len(test_texts),
            "vocab_size": vocab_size,
            "test_accuracy": round(ml_acc, 4),
            "rule_baseline_accuracy": round(rule_acc, 4),
        }
        model.save(WEIGHTS_PATH, VOCAB_PATH)
        print(f"\nsaved weights : {WEIGHTS_PATH}")
        print(f"saved vocab   : {VOCAB_PATH}")
        print("enable with   : INTENT_CLASSIFIER_BACKEND=ml (rule|ml|dnn|hybrid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
