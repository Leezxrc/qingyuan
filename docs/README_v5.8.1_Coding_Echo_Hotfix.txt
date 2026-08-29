清渊 v5.8.1 — Coding Session / TTS 自回声热修
==================================================

本包只包含代码与测试脚本，不包含 data / memory / knowledge / skills /
workspace / STT vocabulary / 模型 / 虚拟环境等持久化内容。

修复 1：只读 Coding Agent 过度申请权限
--------------------------------------
- “只检查/只分析/解释代码，不要修改”现在只申请 file_read。
- 不再为了读两个源码文件申请 code_execute。
- 只读 Coding Session 可在没有 compile/pytest/Git 权限时安全建立与结束。
- Git 基线只在任务真正获得 code_execute 权限时读取。

修复 2：模型忘记 code_finish_session 后误报失败
-----------------------------------------------
- 当模型已经读取完代码并准备回答，却忘记机械调用 code_finish_session，
  AgentCore 会自动补上会话收尾。
- 只读任务会正常结束并自动收回 Task Permit。
- 写入任务仍然不能绕过验证；未验证 revision 会继续要求真实检查。
- 不再把“code_finish_session 尚未调用”这类内部工具状态作为 TTS 错误播报后直接结束。

修复 3：清渊把自己刚说的话当成用户输入
---------------------------------------
- 保留原来的完整/局部回声匹配。
- 新增短句对长句的模糊局部匹配与 bigram 覆盖率。
- 解决 TTS 原句较长，但 STT 只捡到其中一小段且英文技术词略有听错时的漏过滤。
  例如：
    TTS: 任务没有完成：Coding Session 尚未调用 code_finish_session 完成验证。
    STT: 尚未调用coded finish
  现在应被识别为自回声并忽略。
- 强过滤窗口限制在 TTS 结束后的 4 秒内，降低误伤正常后续对话的概率。

安装
----
1. 退出清渊（Frontend / Backend 均应停止）。
2. 解压本 ZIP 到 C:\MyAgent，覆盖同名文件。
3. 不需要重装 SenseVoice / Torch / FunASR。
4. 重新启动清渊。

测试
----
运行：
  C:\MyAgent\tools\test_coding_agent_v581.bat

应看到：
  ALL_TESTS_OK

推荐实际测试：
  清渊，检查你自己的代码，只检查 qingyuan/router.py 和 qingyuan/factory.py，
  告诉我它们分别负责什么，不要修改任何文件。

预期授权只包含：
  读取文件/目录

不应再包含：
  运行代码编译/项目测试/Git只读检查

任务结束后也不应再播报：
  Coding Session 尚未调用 code_finish_session 完成验证
