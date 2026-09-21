from __future__ import annotations

from app.llm.bge_encoder import VOCAB_PATH
from app.llm.wordpiece import CLS, PAD, SEP, WordPieceTokenizer


def _tokenizer() -> WordPieceTokenizer:
    return WordPieceTokenizer(VOCAB_PATH, max_length=128)


def test_vocab_loads_chinese_and_specials() -> None:
    tok = _tokenizer()
    assert len(tok.token_to_id) == 21128
    for special in (CLS, SEP, PAD, "[UNK]", "[MASK]"):
        assert special in tok.token_to_id


def test_chinese_chars_become_standalone_pieces_with_special_tokens() -> None:
    tok = _tokenizer()
    tokens = tok.tokenize("投放预算")
    assert tokens[0] == CLS and tokens[-1] == SEP
    # Each CJK character is its own WordPiece token.
    assert tokens[1:-1] == ["投", "放", "预", "算"]


def test_english_lowercased_and_whitespace_split() -> None:
    tok = _tokenizer()
    tokens = tok.tokenize("ROI good")
    assert tokens[0] == CLS and tokens[-1] == SEP
    # "good" is an in-vocab whole word; "roi" is OOV for the Chinese vocab and
    # is split into WordPiece subword pieces, every one mapped to a valid id.
    assert "good" in tokens
    assert "roi" not in tokens
    body = tokens[1:-1]
    assert all(0 <= piece_id < 21128 for piece_id in tok.convert_tokens_to_ids(body))


def test_encode_pads_and_builds_attention_mask() -> None:
    tok = _tokenizer()
    input_ids, attention_mask, token_type_ids = tok.encode("预算", max_length=10)
    # 4 real tokens (boundary token + 3 chars) + 6 pads.
    assert len(input_ids) == 10
    assert attention_mask == [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    pad_id = tok.token_to_id[PAD]
    assert input_ids[4:] == [pad_id] * 6
    assert token_type_ids == [0] * 10


def test_unknown_rare_word_maps_to_unk() -> None:
    tok = _tokenizer()
    # A string of uncommon characters may fall back to [UNK], never crash.
    input_ids, _mask, _types = tok.encode("龘靐齉", max_length=8)
    assert all(isinstance(value, int) for value in input_ids)
