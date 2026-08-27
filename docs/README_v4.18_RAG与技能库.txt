清渊 v4.18：Local RAG + Skills Library
==================================================

一、本地文档 RAG

文档目录：
C:\MyAgent\knowledge\documents\

支持：
TXT
MD
JSON
CSV
DOCX
PDF（需要 pypdf）

索引：
C:\MyAgent\data\rag_index.json

清渊会：
- 启动时扫描
- 每 60 秒检查新增/修改/删除
- 自动分块
- 用 BM25 做相关片段检索
- 只把最相关的少量片段注入当前 prompt

不会把整份文档一直塞进上下文。


PDF 支持：
如果 PDF 没有被索引，可以运行：

C:\MyAgent\tools\install_rag_pdf_support.bat


二、Skills 技能库

内置：
C:\MyAgent\skills\builtin\

用户技能：
C:\MyAgent\skills\user\

当前内置：
- 微信发送消息
- 浏览器搜索
- 文件整理

Skill 包含：
- name
- description
- triggers
- steps
- required_capabilities
- verification
- safety

Planner 会按当前任务匹配技能。

重要：
Skill 只是“操作经验 / 推荐流程”，
不会自动获得权限。

Task Permit 仍然是唯一操作授权层。


三、当前认知链

Voice / Keyboard
    ↓
Semantic Interpreter
    ↓
Long-term Memory
    ↓
Cognitive Router
    ↓
Relevant Memory
    ↓
Local Document RAG
    ↓
Skill Match
    ↓
Planner
    ↓
Critic
    ↓
Task Permit
    ↓
Executor
    ↓
Replanner
    ↓
Verifier
