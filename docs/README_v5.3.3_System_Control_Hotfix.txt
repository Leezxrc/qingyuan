清渊 v5.3.3：System Control Deterministic Hotfix
============================================================

修复现象：

用户：
“清渊，帮我关机”

旧 v5.3.2 虽然 Router 与工具已经支持 system_power，
但最后仍把任务交给 AgentCore / 8B 模型自由决定。

模型可能直接回答：

“无法帮你关机，当前没有权限……”

这不是 Windows 权限错误。
而是 LLM 没有调用工具。


v5.3.3 改为：

系统级动作不再交给模型自由决定。


用户命令
    ↓
确定性识别 system action
    ↓
begin_request(原始用户命令)
    ↓
authorize_task(
    capabilities=["power_control"],
    targets=["shutdown"]
)
    ↓
第一次 Task Permit
    ↓
system_power("shutdown")
    ↓
Windows Action Host
    ↓
第二次系统级最终确认
    ↓
真正执行


支持确定性动作：

关机 -> shutdown
重启 -> restart
睡眠 -> sleep
锁屏 -> lock
注销 -> logout


关键安全边界：

Brain Backend 仍不能直接执行 shutdown.exe。

真正的系统调用仍只存在于 Windows Local Action Host。

本版只是移除了“让模型自己决定是否执行工具”的不确定性。


正常关机测试应该先看到：

【清渊请求操作确认】
本次申请权限：系统电源/会话控制
本次目标：shutdown

第一次同意后，还应该看到：

【系统级最终确认】
最终动作：立即关闭这台电脑

只有第二次也确认，才会真正关机。


版本：
Frontend / Backend 5.3.3
Protocol 7
