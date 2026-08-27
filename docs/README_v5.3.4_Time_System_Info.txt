清渊 v5.3.4 - 时间 / 只读系统信息补丁（CODE ONLY）
=====================================================

用途
----
让清渊可以通过真实 Windows 本机时间回答并语音播报：
- 现在几点
- 今天几号
- 今天星期几
- 当前日期

本次主要修复
----------
1. system_info 路由保持为“必须调用工具，但不是电脑操作授权任务”。
2. Brain Backend 的 RemoteToolFactory 新增 get_current_time 代理工具。
3. Windows Action Host 新增 get_current_time 白名单入口。
4. SystemTools 从本机 datetime 读取真实日期/时间，不联网、不申请权限。
5. Prompt 明确 system_info 为低风险只读能力，无需 authorize_task。
6. Planner 明确先读取真实系统信息，再回答用户。
7. AgentCore 只认“当前请求”的工具结果，避免上一轮 tool result 串入本轮判断。
8. 版本升级到 5.3.4，Backend Protocol 升级到 8，使前后端握手刷新旧 Backend。

安装
----
1. 完全退出清渊。
2. 将本压缩包解压到 C:\MyAgent\
3. 允许覆盖同名 qingyuan\*.py 文件。
4. 重新启动清渊。
5. 测试："清渊，现在几点了？"

数据安全
--------
本包是 CODE ONLY。
不包含、不覆盖、不删除：
- data\
- memory\
- knowledge\
- RAG 文档/索引数据
- skills 学习数据
- STT vocabulary
- workspace
- 用户视觉学习资料
- 其他用户持久化内容

自检（可选）
------------
在 C:\MyAgent 下运行：
.venv\Scripts\python.exe tools\test_system_info_time.py

预期看到多行 [OK]。
