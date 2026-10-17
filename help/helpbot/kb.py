"""Knowledge base loading and retrieval for the help bot.

The knowledge base is plain markdown under ``help/knowledge/``:

* curated guides written by hand (``00-overview.md`` …)
* generated indexes written by ``help/build_kb.py``
  (``generated/commands.md``, ``generated/help-menu.md``)

Retrieval is a small BM25 index implemented in the standard library — no
embedding API, no extra dependency, no network. Command names such as
``/hunt`` get an exact-match boost because that is how players actually
phrase questions.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import config

#: Longest single chunk. Small enough that a handful of chunks still fit
#: comfortably inside a chat-completion prompt.
MAX_CHUNK_CHARS = 1100
#: BM25 parameters.
K1 = 1.5
B = 0.75

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
    "does", "for", "from", "how", "i", "if", "in", "into", "is", "it",
    "its", "me", "my", "not", "of", "on", "or", "our", "so", "the", "them",
    "then", "there", "these", "they", "this", "to", "us", "was", "we",
    "what", "when", "where", "which", "who", "why", "will", "with", "you",
    "your", "please", "tell", "about", "bot", "forge",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*?)\s*$")
_COMMAND_RE = re.compile(r"/([a-z][a-z0-9_]{1,30})")
#: Commands look like /hunt, /my_team … words after a slash that are
#: followed by a backtick, space, or punctuation in prose.
_SLASH_RE = re.compile(r"(?<![\w/])/([a-z][a-z0-9_]{1,30})\b")


def _stem(token: str) -> str:
    """Very light suffix stripping so query and document wording line up.

    ``breeding`` → ``breed``, ``eggs`` → ``egg``, ``caught`` → ``catch``-ish.
    Deliberately conservative: only the three suffixes that actually
    appear in Forge's vocabulary, and never below 4 characters, so
    short tokens like ``pvp``, ``tm`` and ``xp`` survive untouched.
    """
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    if (len(token) > 3 and token.endswith("s")
            and not token.endswith("ss")):
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed, lightly stemmed."""
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower())
            if t not in _STOPWORDS and (len(t) > 1 or t.isdigit())]


@dataclass
class Chunk:
    id: int
    source: str            # knowledge-relative path, e.g. "02-catching…md"
    heading: str           # full heading trail, e.g. "Catching > Balls"
    text: str
    terms: Counter = field(default_factory=Counter)
    length: int = 0

    @property
    def title(self) -> str:
        return self.heading.rsplit(" > ", 1)[-1] if self.heading else self.source


@dataclass
class Scored:
    chunk: Chunk
    score: float


def _split_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split markdown into (heading_trail, body_lines) sections."""
    sections: list[tuple[str, list[str]]] = []
    trail: list[str] = []
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        if any(ln.strip() for ln in body):
            sections.append((" > ".join(t for t in trail if t), list(body)))
        body = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            flush()
            trail = trail[:level - 1]
            while len(trail) < level:
                trail.append("")
            trail[level - 1] = title
            continue
        body.append(line)
    flush()
    return sections


def _pack(body: list[str], heading: str) -> list[str]:
    """Pack body lines into ~MAX_CHUNK_CHARS chunks on line boundaries."""
    chunks: list[str] = []
    current: list[str] = []
    size = len(heading)
    for line in body:
        if size + len(line) + 1 > MAX_CHUNK_CHARS and current:
            chunks.append("\n".join(current).strip())
            current, size = [], len(heading)
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]


class KnowledgeBase:
    """Load-once, query-many BM25 index over the knowledge folder."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or config.KNOWLEDGE_DIR)
        self.chunks: list[Chunk] = []
        self._by_id: dict[int, Chunk] = {}
        #: command name (no slash) -> chunk ids that document it
        self._commands: dict[str, set[int]] = defaultdict(set)
        #: knowledge file stem -> (relative path, h1 title, full text)
        self._files: dict[str, tuple[str, str, str]] = {}
        self._df: Counter = Counter()
        self._avg_len = 1.0
        self._loaded = False

    # ── loading ─────────────────────────────────────────────────────────

    def load(self, force: bool = False) -> int:
        if self._loaded and not force:
            return len(self.chunks)
        self.chunks, self._by_id = [], {}
        self._commands = defaultdict(set)
        self._files = {}
        self._df = Counter()

        for path in sorted(self.root.rglob("*.md")):
            rel = path.relative_to(self.root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            self._files[path.stem] = (rel, _h1(text), text)
            for heading, body in _split_sections(text.splitlines()):
                for piece in _pack(body, heading):
                    self._add(rel, heading, piece)

        for chunk in self.chunks:
            for term in set(chunk.terms):
                self._df[term] += 1
        total = sum(c.length for c in self.chunks) or 1
        self._avg_len = total / max(len(self.chunks), 1)
        self._loaded = True
        return len(self.chunks)

    def _add(self, source: str, heading: str, text: str) -> None:
        cid = len(self.chunks)
        terms: Counter = Counter()
        # Headings carry extra weight: "Catching > Balls" should beat a
        # stray mention of the word in a long paragraph.
        for term in tokenize(heading) * 3:
            terms[term] += 1
        for term in tokenize(text):
            terms[term] += 1
        chunk = Chunk(id=cid, source=source, heading=heading, text=text,
                      terms=terms, length=max(sum(terms.values()), 1))
        self.chunks.append(chunk)
        self._by_id[cid] = chunk
        for cmd in _SLASH_RE.findall(text):
            self._commands[cmd].add(cid)

    # ── querying ────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 6) -> list[Scored]:
        """BM25 search plus exact-command boosts, best first."""
        self.load()
        terms = tokenize(query)
        if not terms:
            return []
        n = len(self.chunks)
        scores: dict[int, float] = {}
        for term in terms:
            df = self._df.get(term)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for chunk in self.chunks:
                tf = chunk.terms.get(term)
                if not tf:
                    continue
                denom = tf + K1 * (1 - B + B * chunk.length / self._avg_len)
                scores[chunk.id] = scores.get(chunk.id, 0.0) + \
                    idf * (tf * (K1 + 1)) / denom

        # "/hunt", "myteam", "gymbattle" — players type command names.
        for cmd in set(_SLASH_RE.findall(query)) | {
                t for t in terms if t in self._commands}:
            for cid in self._commands.get(cmd, ()):
                scores[cid] = scores.get(cid, 0.0) + 5.0

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [Scored(self._by_id[cid], score)
                for cid, score in ranked[:limit] if score > 0]

    def best_score(self, query: str) -> float:
        hits = self.search(query, limit=1)
        return hits[0].score if hits else 0.0

    def query_coverage(self, query: str) -> float:
        """Fraction of the query's content words that exist in the docs.

        This — not the raw BM25 score — is what separates "shiny odds" from
        "write me a python script". Player phrasing always uses Forge
        vocabulary (coverage 0.86+), while stray questions match only the
        occasional generic word (≤0.75).
        """
        self.load()
        terms = tokenize(query)
        if not terms:
            return 0.0
        hits = sum(1 for term in terms if self._df.get(term))
        return hits / len(terms)

    def command_line(self, name: str) -> str | None:
        """The `- /name — …` index line for a command, if documented."""
        self.load()
        name = name.lower().lstrip("/")
        needle = f"- `/{name}` —"
        for chunk in self.chunks:
            if chunk.source.endswith("commands.md") and needle in chunk.text:
                for line in chunk.text.splitlines():
                    if line.startswith(needle):
                        return line
        return None

    # ── guides ──────────────────────────────────────────────────────────

    def guides(self) -> list[tuple[str, str, int]]:
        """[(stem, h1 title, characters)] for the curated guides."""
        self.load()
        out = []
        for stem, (rel, title, text) in self._files.items():
            if rel.startswith("generated/"):
                continue
            out.append((stem, title, len(text)))
        return sorted(out)

    def guide_text(self, stem: str) -> str | None:
        self.load()
        entry = self._files.get(stem) or self._files.get(_closest(stem, self._files))
        return entry[2] if entry else None

    def guide_title(self, stem: str) -> str:
        self.load()
        entry = self._files.get(stem)
        return entry[1] if entry else stem

    def file_for_term(self, term: str) -> str | None:
        """Best guide stem for a topic word (used by the menu buttons)."""
        self.load()
        term = term.lower()
        if term in self._files:
            return term
        best, best_hits = None, 0
        for stem, (rel, title, text) in self._files.items():
            if rel.startswith("generated/"):
                continue
            hay = f"{stem} {title}".lower()
            hits = sum(1 for t in tokenize(term) if t in hay)
            if hits > best_hits:
                best, best_hits = stem, hits
        return best

    def context_for(self, query: str, budget: int) -> tuple[str, list[str]]:
        """Build the retrieval context block sent to the model."""
        self.load()
        picked: list[Chunk] = []
        used = 0
        for hit in self.search(query, limit=8):
            chunk = hit.chunk
            if any(c.id == chunk.id for c in picked):
                continue
            addition = len(chunk.text) + len(chunk.heading) + 40
            if used + addition > budget and picked:
                continue
            picked.append(chunk)
            used += addition
        if not picked:
            return "", []
        blocks, sources = [], []
        for chunk in picked:
            head = f"### {chunk.heading}" if chunk.heading else f"### {chunk.source}"
            blocks.append(f"{head}\n(source: {chunk.source})\n{chunk.text}")
            if chunk.source not in sources:
                sources.append(chunk.source)
        return "\n\n---\n\n".join(blocks), sources

    def stats(self) -> dict:
        self.load()
        return {
            "chunks": len(self.chunks),
            "files": len(self._files),
            "commands": len(self._commands),
        }


# ── helpers ──────────────────────────────────────────────────────────────

def _h1(text: str) -> str:
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return ""


def _closest(stem: str, files: dict) -> str:
    """Fuzzy fallback so /guide breed still finds 05-breeding."""
    stem = stem.lower()
    for candidate in files:
        if stem in candidate or candidate in stem:
            return candidate
    return stem
