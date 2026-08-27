清渊 v5.2：RAG 2.0
============================================================

一、目标

让清渊不只是“能搜文档”，而是：

先判断相关文档
    ↓
再检索相关片段
    ↓
判断相关度
    ↓
回答
    ↓
告诉用户来源文件


二、文档目录

C:\MyAgent\knowledge\documents\


三、新索引

C:\MyAgent\data\rag_index_v2.json

v5.2 不再依赖旧：

rag_index.json

旧文件可以保留，不影响运行。


四、检索改进

旧版：
所有 chunk 直接一起搜。

新版：

问题
  ↓
Document Ranking
  ↓
筛选最相关文件
  ↓
Chunk Ranking
  ↓
返回最相关片段

这样资料很多以后更不容易串文档。


五、指定文件

如果用户说：

“根据 abc.pdf 告诉我……”

RAG 会强烈优先 abc.pdf。

Prompt 也明确要求：

用户指定某文件时，
不能拿别的文件替它补答案。


六、来源

传给模型的片段包含：

【SOURCE: 文件路径 #chunk-X】

回答使用本地资料时，
模型被要求在回答末尾给：

来源：xxx.pdf


七、低置信度

如果相关度太低：

检索状态：低相关

模型必须告诉用户证据不足，
不能把自己的常识伪装成本地资料内容。


八、支持格式

TXT
MD
JSON
CSV
DOCX
PDF

PDF 仍需要 pypdf。


九、测试工具

查看索引并测试检索：

C:\MyAgent\.venv\Scripts\python.exe
C:\MyAgent\tools\rag_status.py

强制重建：

C:\MyAgent\.venv\Scripts\python.exe
C:\MyAgent\tools\rebuild_rag_index.py


十、后续

v5.2 仍然是轻量本地检索，
没有引入大型向量数据库。

这样做是因为当前机器：
32GB RAM + RTX 3080 10GB

优先保持：
低资源占用
可解释
可维护
不影响 4B / 8B 模型运行

后续资料库变大以后，
再加入 embedding + hybrid retrieval。
