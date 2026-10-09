"""HS 2022 retrieval index: BM25 over English words + char n-gram TF-IDF, fused with RRF.

Each document is one 6-digit subheading, enriched with its heading and chapter
descriptions. Two rankers score a query independently:

- BM25 (rank_bm25) over accent-folded, lightly stemmed English word tokens;
- TF-IDF over character n-grams (3-5, word-bounded), which partially matches
  German/French/Italian cognates ("Zentrifugalpumpe" ~ "centrifugal pump").

Their rankings are merged with reciprocal-rank fusion (Cormack et al., 2009):
score(d) = sum over ranked lists of 1 / (RRF_K + rank). No network, no model download.
"""

from __future__ import annotations

import csv
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

from ..config import get_settings
from ..models import HSCandidate

RRF_K = 60  # standard RRF constant (Cormack, Clarke & Buettcher, SIGIR 2009)
LIST_DEPTH = 100  # each ranked list contributes its top-100 documents to the fusion
RANKERS = ("bm25", "tfidf")

# Function words dropped before ranking: English plus HS boilerplate ("n.e.c. in heading no. 8413",
# "of a kind used for"), and common German/French/Italian ones, matched before accent folding so that
# German "für" is dropped while English "fur" (chapter 43) is kept. German "die" is kept ("die forging").
# Bare numbers are dropped too: HS thresholds ("exceeding 750W") are magnitudes, and a lexical match
# ("100 W" ~ "of an age exceeding 100 years") is noise.
_STOPWORDS_BY_LANG = {
    "en": "a an and any are as at be being by for from in into is it its not of on or other than that the their "
    "thereof to with without whether including excluding nec no heading headings item items subheading chapter "
    "kind used use such",
    "de": "der das den dem des ein eine einer eines einem einen und oder mit ohne für fuer aus von vom zum zur im am "
    "auf bei nach zu als bis pro inkl",
    "fr": "le la les un une du de et ou avec sans pour en au aux sur par dans à",
    "it": "il lo gli una uno di del della dei degli delle da dal dalla con senza per su nel nella alla",
}
_STOPWORDS = frozenset(" ".join(_STOPWORDS_BY_LANG.values()).split())
_WORD_RE = re.compile(r"[^\W_]+")


def fold(text: str) -> str:
    """Case-fold and strip accents ("Flüssigkeit" -> "flussigkeit", "ß" -> "ss")."""
    text = text.casefold()
    if text.isascii():
        return text
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    """Content words: case-folded, function words and bare numbers removed, accents folded.

    NFC first: in decomposed text (macOS input, "u" + combining diaeresis) the combining mark is not a word
    character and would split "Kühlwasser" into "ku" + "hlwasser".
    """
    text = unicodedata.normalize("NFC", text).casefold()
    return [fold(w) for w in _WORD_RE.findall(text) if len(w) > 1 and not w.isdigit() and w not in _STOPWORDS]


def _stem(token: str) -> str:
    """Tiny English plural stemmer, applied identically to documents and queries."""
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es"):
        token = token[:-2]
    elif token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    if token.endswith("e") and len(token) > 3:
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Word tokens for BM25: content words with plurals stemmed."""
    return [_stem(w) for w in words(text)]


def normalise_hs6(code: object) -> str:
    """'8413.70' / ' 841370 ' / 841370 -> '841370' (no validation)."""
    if isinstance(code, int):
        return f"{code:06d}"
    return re.sub(r"[\s.]", "", str(code))


@dataclass(frozen=True)
class Fusion:
    """Result of fusing several ranked lists; `top1` holds each list's leader (None if empty)."""

    candidates: list[HSCandidate]
    n_lists: int
    top1: list[str | None]


class HSIndex:
    """In-memory hybrid retrieval index over the 6-digit HS 2022 subheadings."""

    def __init__(self, descriptions: dict[str, str]):
        self._desc = descriptions
        self._codes = sorted(c for c in descriptions if len(c) == 6)
        cache = {code: words(text) for code, text in descriptions.items()}
        docs = [[w for c in (code, code[:4], code[:2]) for w in cache.get(c, [])] for code in self._codes]
        self._bm25 = BM25Okapi([[_stem(w) for w in doc] for doc in docs])
        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=False, dtype=np.float32
        )
        self._matrix = self._vectorizer.fit_transform([" ".join(doc) for doc in docs])

    @classmethod
    def load(cls, data_dir: Path | None = None) -> HSIndex:
        """Build the index from data/hs/hs2022.csv (columns hscode, level, parent, section, description).

        Rows of section 'TOTAL' (the UN Comtrade aggregates 'TOTAL' and 99/9999/999999 'Commodities
        not specified according to kind') are not HS 2022 codes and are skipped.
        """
        path = (data_dir or get_settings().data_dir) / "hs" / "hs2022.csv"
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["level"] in ("2", "4", "6") and r["section"] != "TOTAL"]
        return cls({r["hscode"]: r["description"].strip() for r in rows})

    # -- public -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._codes)

    def valid(self, hs6: str) -> bool:
        """True if `hs6` is a 6-digit subheading of HS 2022 (dots/spaces tolerated)."""
        code = normalise_hs6(hs6)
        return len(code) == 6 and code in self._desc

    def describe(self, hs6: str) -> str:
        """'chapter > heading > subheading' descriptions. Raises KeyError for unknown codes."""
        code = normalise_hs6(hs6)
        if not self.valid(code):
            raise KeyError(f"not an HS 2022 subheading: {hs6!r}")
        return " > ".join(self._desc[c] for c in (code[:2], code[:4], code) if c in self._desc)

    def search(self, text: str, k: int = 10, chapters: list[str] | None = None) -> list[HSCandidate]:
        """Top-k subheadings for one query, fused over both rankers."""
        return self.fuse([text], k=k, chapters=chapters).candidates

    def fuse(self, texts: list[str], k: int = 10, chapters: list[str] | None = None) -> Fusion:
        """RRF over both rankers for every distinct query text (e.g. raw text + English rewrite).

        `chapters` restricts results to codes starting with any of the given prefixes.
        """
        queries = list(dict.fromkeys(q for q in (" ".join(t.split()) for t in texts) if q))
        allowed = self._allowed(chapters)
        scores: dict[int, float] = {}
        top1: list[str | None] = []
        for query in queries:
            for ranking in (self._rank_bm25(query, allowed), self._rank_tfidf(query, allowed)):
                top1.append(self._codes[ranking[0]] if len(ranking) else None)
                for rank, i in enumerate(ranking, start=1):
                    scores[int(i)] = scores.get(int(i), 0.0) + 1.0 / (RRF_K + rank)
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        candidates = [
            HSCandidate(hs6=self._codes[i], description=self._desc[self._codes[i]], score=s, source="fused")
            for i, s in best
        ]
        return Fusion(candidates=candidates, n_lists=len(RANKERS) * len(queries), top1=top1)

    # -- internals --------------------------------------------------------
    def _allowed(self, chapters: list[str] | None) -> np.ndarray | None:
        if not chapters:
            return None
        prefixes = tuple(normalise_hs6(c) for c in chapters)
        return np.fromiter((c.startswith(prefixes) for c in self._codes), dtype=bool, count=len(self._codes))

    @staticmethod
    def _top(scores: np.ndarray, allowed: np.ndarray | None) -> np.ndarray:
        """Indices with a positive score, best first (ties -> lower code), at most LIST_DEPTH."""
        if allowed is not None:
            scores = np.where(allowed, scores, 0.0)
        order = np.argsort(-scores, kind="stable")[:LIST_DEPTH]
        return order[scores[order] > 0]

    def _rank_bm25(self, query: str, allowed: np.ndarray | None) -> np.ndarray:
        tokens = tokenize(query)
        if not tokens:
            return np.empty(0, dtype=int)
        return self._top(np.asarray(self._bm25.get_scores(tokens), dtype=float), allowed)

    def _rank_tfidf(self, query: str, allowed: np.ndarray | None) -> np.ndarray:
        vec = self._vectorizer.transform([" ".join(words(query))])
        return self._top((self._matrix @ vec.T).toarray().ravel(), allowed)


_index: HSIndex | None = None
_lock = threading.Lock()


def get_index() -> HSIndex:
    """Process-wide index singleton, built on first use from Settings.data_dir."""
    global _index
    with _lock:
        if _index is None:
            _index = HSIndex.load()
        return _index
