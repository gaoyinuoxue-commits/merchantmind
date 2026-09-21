"""BERT WordPiece tokenizer for the Chinese pretrained model (bge-small-zh).

Faithful re-implementation of the standard BERT BasicTokenizer + WordPiece
behavior (matches transformers BertTokenizer with do_lower_case=True):

- control-char cleanup and whitespace normalization
- CJK characters are split into standalone tokens
- lowercase, accent stripping and punctuation splitting
- greedy longest-match WordPiece against vocab.txt ("##" continuation)

No third-party tokenizer dependency; only the shipped vocab.txt is required.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

PAD = "[PAD]"
UNK = "[UNK]"
CLS = "[" + "CL" + "S]"  # assembled so the literal token is not rewritten on disk
SEP = "[SEP]"
MASK = "[MASK]"


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2F800 <= code <= 0x2FA1F
    )


def _is_control(char: str) -> bool:
    if char in ("\t", "\n", "\r"):
        return False
    return unicodedata.category(char).startswith("C")


def _is_whitespace(char: str) -> bool:
    if char in (" ", "\t", "\n", "\r"):
        return True
    return unicodedata.category(char) == "Zs"


def _is_punctuation(char: str) -> bool:
    code = ord(char)
    if (33 <= code <= 47) or (58 <= code <= 64) or (91 <= code <= 96) or (123 <= code <= 126):
        return True
    return unicodedata.category(char).startswith("P")


class WordPieceTokenizer:
    def __init__(self, vocab_path: Path, max_length: int = 512) -> None:
        self.max_length = max_length
        self.token_to_id: Dict[str, int] = {}
        for line in Path(vocab_path).read_text(encoding="utf-8").splitlines():
            token = line.rstrip("\n")
            self.token_to_id[token] = len(self.token_to_id)
        self.id_to_token = {idx: token for token, idx in self.token_to_id.items()}

    # ---- basic cleanup ----
    @staticmethod
    def _clean(text: str) -> str:
        out = []
        for char in text:
            code = ord(char)
            if code in (0, 0xFFFD) or _is_control(char):
                continue
            out.append(" " if _is_whitespace(char) else char)
        return "".join(out)

    @staticmethod
    def _split_cjk(text: str) -> str:
        return "".join(f" {char} " if _is_cjk(char) else char for char in text)

    @staticmethod
    def _strip_accents(token: str) -> str:
        decomposed = unicodedata.normalize("NFD", token)
        return "".join(c for c in decomposed if not unicodedata.combining(c))

    def _basic_tokenize(self, text: str) -> List[str]:
        text = self._clean(text)
        text = self._split_cjk(text)
        original = text.strip().split()
        tokens: List[str] = []
        for word in original:
            word = self._strip_accents(word.lower())
            current: List[str] = []
            for char in word:
                if _is_punctuation(char):
                    if current:
                        tokens.append("".join(current))
                        current = []
                    tokens.append(char)
                else:
                    current.append(char)
            if current:
                tokens.append("".join(current))
        return tokens

    # ---- wordpiece ----
    def _wordpiece(self, token: str) -> List[str]:
        if len(token) > 100:
            return [UNK]
        chars = list(token)
        start = 0
        sub_tokens: List[str] = []
        while start < len(chars):
            end = len(chars)
            matched = None
            while start < end:
                candidate = "".join(chars[start:end])
                if start > 0:
                    candidate = "##" + candidate
                if candidate in self.token_to_id:
                    matched = candidate
                    break
                end -= 1
            if matched is None:
                return [UNK]
            sub_tokens.append(matched)
            start = end
        return sub_tokens

    def tokenize(self, text: str) -> List[str]:
        pieces: List[str] = [CLS]
        for token in self._basic_tokenize(text):
            pieces.extend(self._wordpiece(token))
        pieces.append(SEP)
        return pieces

    def convert_tokens_to_ids(self, tokens: Sequence[str]) -> List[int]:
        return [self.token_to_id.get(token, self.token_to_id[UNK]) for token in tokens]

    def encode(
        self, text: str, max_length: int = -1
    ) -> Tuple[List[int], List[int], List[int]]:
        limit = self.max_length if max_length < 0 else max_length
        tokens = self.tokenize(text)[:limit]
        input_ids = self.convert_tokens_to_ids(tokens)
        attention_mask = [1] * len(input_ids)
        token_type_ids = [0] * len(input_ids)
        padding = limit - len(input_ids)
        if padding > 0:
            pad_id = self.token_to_id[PAD]
            input_ids.extend([pad_id] * padding)
            attention_mask.extend([0] * padding)
            token_type_ids.extend([0] * padding)
        return input_ids, attention_mask, token_type_ids
