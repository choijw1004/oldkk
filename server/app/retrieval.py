"""Small, inspectable lexical retriever. No model or network is needed to index."""

import json
import math
import re
from collections import Counter
from pathlib import Path

from .models import Expression, Reference, Style


# These are editorial seed classifications, not verified age/generation labels.
THEATRICAL_IDS = {36, 46, 63, 64, 67, 69, 70, 110, 121, 126, 127, 129, 130, 131, 136, 140}
WORDPLAY_IDS = {101, 102, 103, 104}


def classify_style(number: int) -> Style:
    if 91 <= number <= 100 or 141 <= number <= 150:
        return "retro_chat"
    if number in THEATRICAL_IDS:
        return "theatrical"
    if number in WORDPLAY_IDS:
        return "wordplay"
    return "daily"


def tokens(text: str) -> list[str]:
    words = re.findall(r"[가-힣a-z0-9]+", text.lower())
    result = []
    for word in words:
        if len(word) < 2:
            continue
        result.append("w:" + word)
        result.extend("c:" + word[i:i + 2] for i in range(len(word) - 1))
    return result


class ExpressionStore:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.items = [
            Expression(**row, style=classify_style(int(row["id"].rsplit("-", 1)[1])))
            for row in data["expressions"]
        ]
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate expression IDs")
        self.by_id = {item.id: item for item in self.items}
        self.documents = [Counter(tokens(" ".join([
            item.expression, item.neutral_expression, item.situation, item.category,
        ]))) for item in self.items]
        self.lengths = [sum(doc.values()) for doc in self.documents]
        self.avg_length = sum(self.lengths) / max(len(self.lengths), 1)
        frequencies = Counter(token for doc in self.documents for token in doc)
        self.idf = {
            token: math.log(1 + (len(self.items) - count + 0.5) / (count + 0.5))
            for token, count in frequencies.items()
        }

    def search(self, query: str, style: Style | None = None, limit: int = 6) -> list[Reference]:
        query_tokens = set(tokens(query))
        results = []
        for item, document, length in zip(self.items, self.documents, self.lengths):
            if style and item.style != style:
                continue
            score = 0.0
            for token in query_tokens:
                count = document.get(token, 0)
                if count:
                    norm = count + 1.5 * (0.25 + 0.75 * length / self.avg_length)
                    score += self.idf[token] * count * 2.5 / norm
            if score >= 1.4:
                results.append(Reference(**item.model_dump(), retrieval_score=round(score, 4)))
        return sorted(results, key=lambda item: (-item.retrieval_score, item.id))[:limit]

    def browse(self, query: str, style: Style | None) -> list[Expression]:
        query = query.strip().lower()
        return [item for item in self.items
                if (not style or item.style == style)
                and (not query or query in " ".join([
                    item.expression, item.neutral_expression, item.situation, item.category,
                ]).lower())]

    def stats(self) -> dict:
        return {
            "total": len(self.items),
            "styles": dict(Counter(item.style for item in self.items)),
            "dataset_status": "unreviewed_seed",
        }
