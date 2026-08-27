from pathlib import Path

from qingyuan.local_rag import (
    INDEX_FILE,
    LocalDocumentRAG,
)


if INDEX_FILE.exists():
    INDEX_FILE.unlink()

rag = LocalDocumentRAG()

rag.rebuild_if_needed()

print(
    "RAG 2.0 索引已重建："
)
print(
    rag.status_text()
)
