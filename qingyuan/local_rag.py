import csv
import json
import math
import re
import threading
import time
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


DOCUMENTS_DIR = Path(
    r"C:\MyAgent\knowledge\documents"
)

INDEX_FILE = Path(
    r"C:\MyAgent\data\rag_index_v2.json"
)

SUPPORTED = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".docx",
    ".pdf",
}


def _tokenize(text):
    raw = str(text).lower()

    ascii_tokens = re.findall(
        r"[a-z0-9_./:\\\-]+",
        raw,
    )

    chinese = "".join(
        re.findall(
            r"[\u4e00-\u9fff]",
            raw,
        )
    )

    chinese_tokens = []

    if chinese:
        if len(chinese) == 1:
            chinese_tokens.append(
                chinese
            )
        else:
            chinese_tokens.extend(
                chinese[i:i+2]
                for i in range(
                    len(chinese) - 1
                )
            )

    return ascii_tokens + chinese_tokens


def _split_sentences(text):
    parts = re.split(
        r"(?<=[。！？!?；;])|\n+",
        str(text),
    )

    return [
        p.strip()
        for p in parts
        if p.strip()
    ]


def _chunk_text(
    text,
    chunk_chars=900,
    overlap_chars=160,
):
    sentences = _split_sentences(
        text
    )

    if not sentences:
        return []

    chunks = []
    current = ""

    for sentence in sentences:
        candidate = (
            sentence
            if not current
            else current + "\n" + sentence
        )

        if (
            current
            and len(candidate)
            > chunk_chars
        ):
            chunks.append(
                current.strip()
            )

            tail = (
                current[-overlap_chars:]
                if overlap_chars > 0
                else ""
            )

            current = (
                tail
                + "\n"
                + sentence
            ).strip()

        else:
            current = candidate

    if current:
        chunks.append(
            current.strip()
        )

    final = []

    for chunk in chunks:
        if len(chunk) <= chunk_chars * 1.5:
            final.append(chunk)
            continue

        step = max(
            1,
            chunk_chars - overlap_chars,
        )

        for i in range(
            0,
            len(chunk),
            step,
        ):
            part = chunk[
                i:i + chunk_chars
            ].strip()

            if part:
                final.append(part)

    return final


class LocalDocumentRAG:
    """
    RAG 2.0

    特性：
    - 增量索引
    - 文档级召回 + 片段级召回
    - 文件名/路径定向
    - 本地来源标注
    - 低置信度拒绝硬答
    - 文档删除自动清理索引
    """

    def __init__(self):
        self._lock = (
            threading.RLock()
        )

        self._index = {
            "version": 2,
            "documents": {},
            "chunks": [],
        }

        DOCUMENTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        INDEX_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._load_index()

    # ---------------- extraction ----------------

    @staticmethod
    def _read_text_file(path):
        for encoding in (
            "utf-8",
            "utf-8-sig",
            "gb18030",
            "cp1252",
        ):
            try:
                return path.read_text(
                    encoding=encoding
                )
            except Exception:
                continue

        return ""

    @staticmethod
    def _read_json(path):
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            return json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )

        except Exception:
            return (
                LocalDocumentRAG
                ._read_text_file(
                    path
                )
            )

    @staticmethod
    def _read_csv(path):
        rows = []

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                reader = csv.reader(f)

                for row in reader:
                    rows.append(
                        " | ".join(
                            str(x)
                            for x in row
                        )
                    )

            return "\n".join(rows)

        except Exception:
            return (
                LocalDocumentRAG
                ._read_text_file(
                    path
                )
            )

    @staticmethod
    def _read_docx(path):
        try:
            with zipfile.ZipFile(
                path,
                "r",
            ) as z:
                xml = z.read(
                    "word/document.xml"
                )

            root = ET.fromstring(
                xml
            )

            ns = {
                "w": (
                    "http://schemas.openxmlformats.org/"
                    "wordprocessingml/2006/main"
                )
            }

            paragraphs = []

            for p in root.findall(
                ".//w:p",
                ns,
            ):
                texts = [
                    t.text or ""
                    for t in p.findall(
                        ".//w:t",
                        ns,
                    )
                ]

                value = "".join(
                    texts
                ).strip()

                if value:
                    paragraphs.append(
                        value
                    )

            return "\n\n".join(
                paragraphs
            )

        except Exception:
            return ""

    @staticmethod
    def _read_pdf(path):
        try:
            from pypdf import PdfReader

            reader = PdfReader(
                str(path)
            )

            pages = []

            for page_number, page in enumerate(
                reader.pages,
                1,
            ):
                try:
                    value = (
                        page.extract_text()
                        or ""
                    ).strip()
                except Exception:
                    value = ""

                if value:
                    pages.append(
                        f"[Page {page_number}]\n"
                        + value
                    )

            return "\n\n".join(
                pages
            )

        except Exception:
            return ""

    def _extract(self, path):
        suffix = (
            path.suffix.lower()
        )

        if suffix in {
            ".txt",
            ".md",
            ".markdown",
        }:
            return self._read_text_file(
                path
            )

        if suffix == ".json":
            return self._read_json(
                path
            )

        if suffix == ".csv":
            return self._read_csv(
                path
            )

        if suffix == ".docx":
            return self._read_docx(
                path
            )

        if suffix == ".pdf":
            return self._read_pdf(
                path
            )

        return ""

    # ---------------- index ----------------

    def _load_index(self):
        try:
            if INDEX_FILE.exists():
                data = json.loads(
                    INDEX_FILE.read_text(
                        encoding="utf-8"
                    )
                )

                if (
                    isinstance(data, dict)
                    and data.get(
                        "version"
                    ) == 2
                ):
                    self._index = data

        except Exception:
            pass

    def _save_index(self):
        INDEX_FILE.write_text(
            json.dumps(
                self._index,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _fingerprint(path):
        stat = path.stat()

        return (
            f"{stat.st_size}:"
            f"{int(stat.st_mtime_ns)}"
        )

    @staticmethod
    def _document_terms(
        relative,
        title,
        text,
    ):
        sample = text[:6000]

        return _tokenize(
            f"{relative}\n{title}\n{sample}"
        )

    def rebuild_if_needed(self):
        with self._lock:
            documents = dict(
                self._index.get(
                    "documents",
                    {},
                )
            )

            old_chunks = list(
                self._index.get(
                    "chunks",
                    [],
                )
            )

            current_paths = {}

            for path in (
                DOCUMENTS_DIR
                .rglob("*")
            ):
                if (
                    path.is_file()
                    and path.suffix.lower()
                    in SUPPORTED
                ):
                    relative = str(
                        path.relative_to(
                            DOCUMENTS_DIR
                        )
                    )

                    current_paths[
                        relative
                    ] = path

            changed = False

            removed = (
                set(
                    documents.keys()
                )
                - set(
                    current_paths.keys()
                )
            )

            if removed:
                changed = True

                for key in removed:
                    documents.pop(
                        key,
                        None,
                    )

                old_chunks = [
                    c
                    for c in old_chunks
                    if c.get(
                        "document"
                    )
                    not in removed
                ]

            for relative, path in (
                current_paths.items()
            ):
                fingerprint = (
                    self._fingerprint(
                        path
                    )
                )

                old = documents.get(
                    relative,
                    {},
                )

                if (
                    old.get(
                        "fingerprint"
                    )
                    == fingerprint
                ):
                    continue

                changed = True

                old_chunks = [
                    c
                    for c in old_chunks
                    if c.get(
                        "document"
                    )
                    != relative
                ]

                text = self._extract(
                    path
                )

                chunks = _chunk_text(
                    text
                )

                doc_chunk_ids = []

                for index, chunk in enumerate(
                    chunks
                ):
                    chunk_id = (
                        f"{relative}#{index}"
                    )

                    doc_chunk_ids.append(
                        chunk_id
                    )

                    old_chunks.append({
                        "id": chunk_id,
                        "document": relative,
                        "title": path.stem,
                        "suffix": (
                            path.suffix.lower()
                        ),
                        "chunk_index": index,
                        "text": chunk,
                        "tokens": _tokenize(
                            chunk
                        ),
                    })

                documents[
                    relative
                ] = {
                    "fingerprint": (
                        fingerprint
                    ),
                    "title": (
                        path.stem
                    ),
                    "suffix": (
                        path.suffix.lower()
                    ),
                    "chunks": (
                        doc_chunk_ids
                    ),
                    "indexed_at": (
                        time.time()
                    ),
                    "characters": (
                        len(text)
                    ),
                    "terms": (
                        self._document_terms(
                            relative,
                            path.stem,
                            text,
                        )
                    ),
                }

                print(
                    f"\n[RAG 2.0] 已索引："
                    f"{relative} "
                    f"({len(chunks)} chunks)"
                )

            if changed:
                self._index = {
                    "version": 2,
                    "documents": (
                        documents
                    ),
                    "chunks": (
                        old_chunks
                    ),
                }

                self._save_index()

            return changed

    def start_watcher(
        self,
        stop_event,
        interval_seconds=60,
    ):
        def worker():
            self.rebuild_if_needed()

            while not stop_event.wait(
                interval_seconds
            ):
                try:
                    self.rebuild_if_needed()
                except Exception as e:
                    print(
                        f"\n[RAG 2.0] "
                        f"索引更新失败：{e}"
                    )

        thread = threading.Thread(
            target=worker,
            name="qingyuan-rag2-indexer",
            daemon=True,
        )

        thread.start()

        return thread

    # ---------------- ranking ----------------

    @staticmethod
    def _bm25_score(
        query_tokens,
        docs_tokens,
    ):
        if not docs_tokens:
            return []

        N = len(
            docs_tokens
        )

        df = Counter()

        for tokens in docs_tokens:
            for token in set(
                tokens
            ):
                df[token] += 1

        avgdl = (
            sum(
                len(tokens)
                for tokens in docs_tokens
            )
            / max(
                1,
                N,
            )
        )

        k1 = 1.5
        b = 0.75

        scores = []

        for tokens in docs_tokens:
            tf = Counter(
                tokens
            )

            dl = len(
                tokens
            )

            score = 0.0

            for token in query_tokens:
                n = df.get(
                    token,
                    0,
                )

                if n <= 0:
                    continue

                idf = math.log(
                    1
                    + (
                        N - n + 0.5
                    )
                    / (
                        n + 0.5
                    )
                )

                freq = tf.get(
                    token,
                    0,
                )

                denom = (
                    freq
                    + k1
                    * (
                        1
                        - b
                        + b
                        * dl
                        / max(
                            1.0,
                            avgdl,
                        )
                    )
                )

                if denom > 0:
                    score += (
                        idf
                        * freq
                        * (
                            k1 + 1
                        )
                        / denom
                    )

            scores.append(
                score
            )

        return scores

    @staticmethod
    def _extract_requested_filename(
        query,
    ):
        raw = str(query)

        quoted = re.findall(
            r"[“\"']([^”\"']+\.(?:pdf|docx|txt|md|json|csv))[”\"']",
            raw,
            flags=re.I,
        )

        if quoted:
            return quoted[-1]

        match = re.search(
            r"([^\s，。！？]+?\.(?:pdf|docx|txt|md|json|csv))",
            raw,
            flags=re.I,
        )

        if match:
            return match.group(1)

        return ""

    def _rank_documents(
        self,
        query,
        limit=6,
    ):
        q_tokens = _tokenize(
            query
        )

        with self._lock:
            documents = dict(
                self._index.get(
                    "documents",
                    {},
                )
            )

        if not documents:
            return []

        names = list(
            documents.keys()
        )

        token_lists = [
            documents[name].get(
                "terms",
                [],
            )
            for name in names
        ]

        scores = self._bm25_score(
            q_tokens,
            token_lists,
        )

        requested_file = (
            self._extract_requested_filename(
                query
            )
        ).lower()

        ranked = []

        lower_query = (
            str(query).lower()
        )

        for name, base_score in zip(
            names,
            scores,
        ):
            item = documents[
                name
            ]

            score = float(
                base_score
            )

            title = str(
                item.get(
                    "title",
                    "",
                )
            ).lower()

            lower_name = (
                name.lower()
            )

            if (
                title
                and title in lower_query
            ):
                score += 8.0

            if (
                lower_name
                and lower_name
                in lower_query
            ):
                score += 12.0

            if requested_file:
                if (
                    lower_name.endswith(
                        requested_file
                    )
                    or title
                    == Path(
                        requested_file
                    ).stem.lower()
                ):
                    score += 50.0
                else:
                    score -= 10.0

            ranked.append(
                (
                    score,
                    name,
                    item,
                )
            )

        ranked.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        return ranked[
            :limit
        ]

    def search(
        self,
        query,
        limit=5,
    ):
        raw_query = str(
            query
        ).strip()

        if not raw_query:
            return []

        self.rebuild_if_needed()

        ranked_docs = (
            self._rank_documents(
                raw_query,
                limit=6,
            )
        )

        if not ranked_docs:
            return []

        selected_docs = {
            name
            for score, name, _
            in ranked_docs
            if score > 0
        }

        if not selected_docs:
            selected_docs = {
                ranked_docs[0][1]
            }

        with self._lock:
            chunks = [
                c
                for c in self._index.get(
                    "chunks",
                    [],
                )
                if c.get(
                    "document"
                )
                in selected_docs
            ]

        if not chunks:
            return []

        q_tokens = _tokenize(
            raw_query
        )

        token_lists = [
            c.get(
                "tokens",
                [],
            )
            for c in chunks
        ]

        chunk_scores = (
            self._bm25_score(
                q_tokens,
                token_lists,
            )
        )

        doc_score_map = {
            name: score
            for score, name, _
            in ranked_docs
        }

        requested_file = (
            self._extract_requested_filename(
                raw_query
            )
        ).lower()

        scored = []

        for chunk, base_score in zip(
            chunks,
            chunk_scores,
        ):
            score = float(
                base_score
            )

            doc_name = str(
                chunk.get(
                    "document",
                    "",
                )
            )

            score += (
                max(
                    0.0,
                    doc_score_map.get(
                        doc_name,
                        0.0,
                    )
                )
                * 0.35
            )

            text = str(
                chunk.get(
                    "text",
                    "",
                )
            ).lower()

            lower_query = (
                raw_query.lower()
            )

            if (
                lower_query
                and len(
                    lower_query
                ) >= 4
                and lower_query in text
            ):
                score += 8.0

            if requested_file:
                if (
                    doc_name.lower()
                    .endswith(
                        requested_file
                    )
                ):
                    score += 20.0

            scored.append(
                (
                    score,
                    chunk,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        results = []

        for rank, (
            score,
            chunk,
        ) in enumerate(
            scored[:limit],
            1,
        ):
            results.append({
                "rank": rank,
                "score": round(
                    score,
                    4,
                ),
                "document": (
                    chunk.get(
                        "document"
                    )
                ),
                "title": (
                    chunk.get(
                        "title"
                    )
                ),
                "suffix": (
                    chunk.get(
                        "suffix"
                    )
                ),
                "chunk_index": (
                    chunk.get(
                        "chunk_index"
                    )
                ),
                "text": (
                    chunk.get(
                        "text"
                    )
                ),
            })

        return results

    def retrieve(
        self,
        query,
        limit=5,
    ):
        results = self.search(
            query,
            limit=limit,
        )

        if not results:
            return {
                "confident": False,
                "reason": (
                    "没有检索到相关本地资料。"
                ),
                "results": [],
                "sources": [],
            }

        top_score = float(
            results[0].get(
                "score",
                0,
            )
        )

        confident = (
            top_score >= 1.6
        )

        sources = []

        seen = set()

        for item in results:
            doc = str(
                item.get(
                    "document",
                    "",
                )
            )

            if (
                doc
                and doc not in seen
            ):
                seen.add(
                    doc
                )

                sources.append(
                    doc
                )

        reason = (
            "已检索到较相关的本地资料。"
            if confident
            else
            "检索结果相关度偏低，回答时应明确说明不确定。"
        )

        return {
            "confident": confident,
            "reason": reason,
            "results": results,
            "sources": sources,
        }

    def context_text(
        self,
        query,
        limit=4,
    ):
        pack = self.retrieve(
            query,
            limit=limit,
        )

        results = pack[
            "results"
        ]

        if not results:
            return ""

        lines = [
            "检索状态："
            + (
                "高相关"
                if pack[
                    "confident"
                ]
                else "低相关"
            ),
            "检索说明："
            + pack[
                "reason"
            ],
            "",
        ]

        for item in results:
            source_label = (
                f"{item['document']}"
                f" #chunk-{item['chunk_index']}"
            )

            lines.append(
                f"【SOURCE: {source_label}】"
            )

            lines.append(
                str(
                    item["text"]
                )[:1400]
            )

            lines.append("")

        return "\n".join(
            lines
        ).strip()

    def source_summary(
        self,
        query,
        limit=5,
    ):
        pack = self.retrieve(
            query,
            limit=limit,
        )

        if not pack[
            "results"
        ]:
            return (
                "没有找到相关本地文档。"
            )

        lines = []

        for item in pack[
            "results"
        ]:
            lines.append(
                f"- {item['document']} "
                f"(chunk {item['chunk_index']}, "
                f"score {item['score']})"
            )

        return "\n".join(
            lines
        )

    def status_text(self):
        with self._lock:
            documents = len(
                self._index.get(
                    "documents",
                    {},
                )
            )

            chunks = len(
                self._index.get(
                    "chunks",
                    [],
                )
            )

        return (
            f"{documents} 个文档 / "
            f"{chunks} 个片段"
        )
