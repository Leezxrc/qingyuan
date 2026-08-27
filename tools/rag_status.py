from qingyuan.local_rag import (
    LocalDocumentRAG,
)


rag = LocalDocumentRAG()

rag.rebuild_if_needed()

print()
print("RAG 2.0 状态：")
print(rag.status_text())

query = input(
    "\n输入测试问题（直接回车退出）："
).strip()

if query:
    print()
    print(
        rag.source_summary(
            query
        )
    )
