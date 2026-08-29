清渊 v5.8.0 — Coding Agent / Self-Development Loop Phase 1
============================================================

目标
----
让清渊在用户明确要求时，能够真正进入一个受保护的“代码任务”闭环：
读取项目 -> 制定最小修改 -> 写入代码 -> 运行检查 -> 查看 diff -> 验证完成；
如果无法修好，可只回滚本次 Coding Session 自己触碰的文件。

本版不是“无限自我改写”。所有真实读写和代码检查仍受 Task Permit 约束。

新增能力
--------
1. coding 意图路由
   - “修改/修复/重构项目代码”进入 Coding Agent。
   - “给清渊/给自己增加功能”进入 Coding Agent。
   - “检查自己的代码，只检查不要修改”可进入只读 Coding Agent。
   - 普通“帮我写一段 Python 示例”仍是 chat，不会碰电脑文件。

2. Coding Session
   - code_begin_session
   - code_session_status
   - code_project_tree
   - code_read_file
   - code_write_file
   - code_git_status
   - code_git_diff
   - code_run_checks
   - code_rollback
   - code_finish_session

3. 验证门
   - 只要本会话真正修改过文件，最新 revision 必须通过 compile / pytest / unittest
     中至少一种检查，code_finish_session 才会返回 CODING_SESSION_FINISHED。
   - 旧 revision 的成功检查不能给后来再次修改的代码“背书”。

4. 回滚
   - 每个文件第一次被本 Coding Session 修改前，会把原始字节保存在进程内存里。
   - code_rollback 只恢复本会话自己触碰的文件。
   - 不使用 git reset，不会把用户原先已有的未提交改动一起抹掉。

5. Git
   - 可以只读获取 HEAD / status / diff。
   - 不自动 git add / commit / push / reset。
   - .git 目录本身禁止 Coding Agent 访问。

6. 自主技能学习
   - 成功 Coding 任务仍会走现有 Skill Learning 流程。
   - 至少重复成功达到既有阈值后才可能晋升长期技能。
   - Coding 技能学习前会移除源码正文、git diff、项目树等内容，只保留流程证据。
   - 学到的是“怎么做这类任务的流程”，不是权限，也不是用户源码。

安全边界
--------
- 不提供任意 shell / cmd / PowerShell 命令执行工具。
- code_run_checks 只允许：compile / pytest / unittest。
- compile 只验证 Python；如果当前 revision 含非 Python 修改，不允许用 Python compile 假装整体验证通过。
- pytest / unittest 会执行项目测试代码，因此属于 code_execute 权限范围。
- 写入仅限当前 Coding Session 项目根目录内的文本代码/配置/文档类型。
- 对清渊自身 C:\MyAgent 开发时，默认保护并拒绝访问：
  data / memory / knowledge / skills / workspace / logs / voice / models /
  stt_env / cosyvoice_env / .venv / CosyVoice 等持久化、模型和运行环境目录。
- .env、credentials、secrets、token 等敏感凭据文件拒绝访问。
- 用户没有明确说“修改清渊/自己/MyAgent”时，模型不能自行把 C:\MyAgent
  选为代码项目根。
- Coding Session 成功结束后会自动回收本次 Task Permit。

本升级包范围
------------
本 ZIP 是 CODE ONLY。
不包含、不覆盖：
- data
- memory
- knowledge
- skills
- workspace
- STT vocabulary
- SenseVoice / Whisper 模型
- CosyVoice 模型/母声
- 其他用户持久化内容

安装
----
1. 完全退出清渊 Frontend / Brain Backend / Action Host。
2. 将 ZIP 内容解压到 C:\MyAgent 并覆盖同名“代码文件”。
3. 重新启动清渊。
4. 可运行：
   C:\MyAgent\tools\test_coding_agent_v580.bat

冒烟测试只使用系统临时目录，不会修改 C:\MyAgent 项目代码或持久化数据。

建议首次真实测试
----------------
只读：
“清渊，检查你自己的代码，只检查 qingyuan/router.py 和 qingyuan/factory.py，不要修改。”

之后再做小范围真实修改，并在 Task Permit 中确认 file_read / file_write / code_execute。

版本
----
QINGYUAN_VERSION = 5.8.0
BACKEND_PROTOCOL_VERSION = 9
