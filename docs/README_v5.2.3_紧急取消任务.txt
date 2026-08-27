清渊 v5.2.3：Emergency Cancel
============================================================

修复：

任务开始执行后，
Frontend 以前会阻塞等待 Backend /command 返回。

所以用户此时输入：

取消
停止
结束任务

虽然进入了输入队列，
但 Frontend 根本没有机会处理。

这是严重的交互和安全问题。


v5.2.3：

Backend 命令改为后台线程运行。

Frontend 主循环在等待期间继续监听紧急控制命令。


支持：

取消
取消任务
停止
停止任务
结束任务
终止任务
中止任务
别做了
别弄了
停下来
stop
cancel
cancel task
stop task


收到取消后：

用户
  ↓
Frontend Emergency Stop
  ↓
POST Backend /cancel
  ↓
POST Action Host /cancel
  ↓
Backend cancel_event
  ↓
Task Permit revoke
  ↓
Desktop task revoke
  ↓
AgentCore 停止后续 tool call
  ↓
回到正常状态


安全原则：

取消命令的优先级高于普通任务。

用户一旦明确取消，
后续尚未执行的工具不能继续调用。


版本：

Frontend / Backend：
5.2.3

Protocol：
3


测试：

1. 发起一个需要操作微信的任务。
2. 同意 Task Permit。
3. 在视觉定位过程中立即输入：

取消

期望：

[紧急停止] 正在取消当前任务并收回权限……
清渊：当前任务已取消。

之后不应该继续发送消息。


注意：

如果某一次 Windows API 调用已经进入操作系统，
无法“撤销已经发生的那个点击”。

但取消信号到达后，
后续动作必须停止。

因此仍然保持：
每一步尽量短小、可验证、可中断。
