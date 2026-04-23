import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
from torch import cuda, bfloat16

class Embedder:
    def __init__(self, model_name: str):
        device = "cuda" if cuda.is_available() else "cpu"
        self.model = SentenceTransformer(
            model_name,
            device=device,
            model_kwargs={"dtype": bfloat16} if device == "cuda" else None,
            tokenizer_kwargs={"padding_side": "left"},
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True, use_fast=True)

    def count_tokens(self, text: str) -> int:
        enc = self.tokenizer(text, return_attention_mask=False, add_special_tokens=True)
        return len(enc["input_ids"])

    def chunk_by_tokens(self, text: str, max_tokens: int, overlap: int):
        """
            Returns list of (start_token_index, end_token_index, chunk_text)
            using the tokenizer so indices align with tokenization used for embeddings.
            This implementation is simple: it tokenizes then decodes token slices.
        """
        if max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if overlap >= max_tokens:
            overlap = max(1, max_tokens - 1)

        # tokenize (get ids)
        enc = self.tokenizer(text, return_tensors=None, add_special_tokens=True, truncation=False)
        token_ids = enc["input_ids"]
        n = len(token_ids)
        if n == 0:
            return []

        chunks = []
        i = 0
        while i < n:
            j = min(i + max_tokens, n)
            # Take slice [i:j)
            chunk_tok_ids = token_ids[i:j]
            # decode token slice back to string
            chunk_text = self.tokenizer.decode(chunk_tok_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
            chunks.append((i, j, chunk_text))

            # If we reached the end, break (prevents reset to 0)
            if j >= n:
                break

            # advance - ensure progress (j - overlap > i)
            next_i = j - overlap
            if next_i <= i:
                # fallback: ensure at least move by 1 token to avoid infinite loop
                next_i = i + 1
            i = next_i

        # return token index ranges and chunk text; caller currently uses only chunk_text.
        return chunks

    def encode(self, texts: list[str], prompt_name: str):
        emb = self.model.encode(
            texts,
            prompt_name=prompt_name,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        emb = np.asarray(emb)
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb
