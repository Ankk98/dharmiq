from __future__ import annotations

from functools import lru_cache

from dharmiq.config.settings import get_settings


@lru_cache
def get_chunk_tokenizer():
    from transformers import AutoTokenizer

    settings = get_settings()
    return AutoTokenizer.from_pretrained(settings.embeddings.local_model_name)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    tokenizer = get_chunk_tokenizer()
    return len(tokenizer.encode(text, add_special_tokens=False))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    tokenizer = get_chunk_tokenizer()
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return text
    truncated_ids = token_ids[:max_tokens]
    return tokenizer.decode(truncated_ids, skip_special_tokens=True).strip()
