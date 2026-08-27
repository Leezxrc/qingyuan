清渊 模块化 v3：Task Permit
================================

核心目标：
权限更大，但没有你的任务授权就什么都不能做。

现在的权限模型：

你下达任务
→ 清渊申请本次任务所需能力 + 目标
→ 确认窗口显示【你的原始命令】
→ 你同意一次
→ 许可证生效
→ 清渊可在本任务内组合所有已批准能力
→ end_task / 超时 / 越界
→ 权限全部收回

支持的任务能力：
- screen_read      读屏
- window_read      看窗口列表
- file_read        读任意已授权路径
- window_control   切换窗口
- mouse            鼠标
- keyboard         键盘
- scroll           滚动
- app_launch       启动程序
- file_write       创建/修改文件
- file_move        移动/重命名
- file_delete      删除

安全边界：
1. authorize_task 的任务描述直接绑定“用户原始命令”，模型不能自行改写。
2. targets 会在确认框中显示，超出 targets 的目标工具会拒绝。
3. 没确认前，受控电脑工具一律拒绝。
4. 任务结束后许可证立即清空。
5. 删除能力不会自动拥有，必须在该任务确认里明确申请 file_delete。
6. 当前版本仍不开放任意 shell/CMD/PowerShell 字符串执行；
   采用结构化工具来降低“做了你没要求的事”的风险。

安装：
将压缩包内容解压覆盖到 C:\MyAgent。

建议测试：
1. 帮我用 Chrome 搜索明日方舟
2. 帮我把微信拉到前台
3. 帮我在微信群聊9652711里发送“你好”
4. 帮我在 C:\Users\<你的用户名>\Desktop 创建 test.txt，写入 hello
5. 帮我删除刚才创建的 test.txt
   ——确认框应该明确显示 file_delete。
