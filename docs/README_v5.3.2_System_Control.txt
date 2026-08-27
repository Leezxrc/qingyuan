清渊 v5.3.2：System Control
============================================================

新增 Windows 固定白名单系统动作：

- shutdown  关机
- restart   重启
- sleep     睡眠
- lock      锁屏
- logout    注销


安全结构：

用户：
“清渊，帮我关机”
    ↓
Router:
system_power
    ↓
Task Permit:
capabilities = ["power_control"]
targets = ["shutdown"]
    ↓
第一次确认
    ↓
system_power("shutdown")
    ↓
第二次【系统级最终确认】
    ↓
Windows Action Host 执行固定白名单动作


重要：

Brain Backend 仍然没有直接操作 Windows 的权限。

system_power 真正执行代码只存在于 Windows Action Host。


没有开放：

- 任意 shell
- 任意 cmd
- 任意 PowerShell
- 模型自定义 shutdown 参数
- 任意系统命令字符串


关机固定为：

shutdown.exe /s /t 0

重启固定为：

shutdown.exe /r /t 0

注销固定为：

shutdown.exe /l

锁屏使用：

Windows LockWorkStation API

睡眠使用：

Windows SetSuspendState API


为什么两次确认：

第一次：
授权本次任务拥有 power_control。

第二次：
确认即将发生的具体不可逆/高影响系统动作。

普通鼠标、键盘、微信权限不能用于关机。
power_control 也不能用于鼠标、文件、微信等其他操作。


测试建议：

先测试风险较低的：

“清渊，锁定电脑”

应该看到：

第一次：
Task Permit
系统电源/会话控制
目标：lock

然后：

第二次：
【系统级最终确认】
最终动作：立即锁定这台电脑


确认第二次后 Windows 会立即锁屏。


关机测试：

“清渊，帮我关机”

第二次确认后会真实立即关机。
请保存当前工作后再测试。


版本：
Frontend / Backend 5.3.2
Protocol 6
