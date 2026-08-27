清渊 v4：Agent Core v2
====================================

新增架构：

User
 ↓
Intent Router
 ↓
Planner
 ↓
Task Permit
 ↓
Executor
 ↓
Verifier
 ↓
Result

Planner
-------
把用户命令拆成内部步骤。
Planner 本身不读取屏幕、不操作电脑、不拥有权限。

例如：
“帮我用 Chrome 搜索明日方舟”

内部计划：
1. 绑定 Chrome
2. 申请窗口控制 + 键盘
3. 新标签搜索
4. 验证真实搜索动作
5. 收回权限

Task Permit
-----------
仍然绑定用户原始命令。
用户确认一次后，只开放本任务需要的 capabilities + targets。

Executor
--------
真正调用工具。
不允许用“我正在操作”代替执行。

Verifier
--------
不相信模型自己说“完成了”。

浏览器：
必须检测到 browser_search_new_tab。

窗口前台：
必须检测到真实窗口切换工具。

微信：
必须检测到 wechat_send_message + 视觉验证结果。

文件：
必须存在真实文件工具结果且没有明确失败。

GUI：
必须存在真实桌面动作记录。

失败时：
Verifier 会阻止清渊宣布成功。

安装
----
解压覆盖到：
C:\MyAgent

原有 STT/TTS/launcher/tray 不需要改。

建议测试
--------
1. 在吗
2. 帮我用 Chrome 搜索明日方舟
3. 帮我把微信拉到前台
4. 帮我在微信群聊9652711中发送一句你好
5. 一个两三步的复杂任务
