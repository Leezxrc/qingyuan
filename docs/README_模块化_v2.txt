清渊 模块化 v2：Execution First
====================================

核心原则：

用户决定“要不要做”，清渊只决定“怎么做”。

电脑操作命令到来时：
- 不允许清渊仅凭语言模型自己的判断直接说“我不能操作”。
- 必须先调用当前 Factory 提供的真实工具。
- 只有工具真实失败后，才可以报告具体失败原因。

新增/修复：
1. Execution-First 执行器：
   明确电脑任务如果没有任何工具调用，会自动强制下一轮进入真实工具执行。
2. 微信发送专用路由：
   “在微信群 X 发 Y” -> wechat_send intent。
3. wechat_send_message：
   搜索聊天 -> 点击聊天 -> 点击输入框 -> 输入 -> Enter -> 视觉验证。
4. 确认语音竞态修复：
   确认结束后返回的下一句话，不再被误标记成“确认语音”。
5. 长期记忆只有与当前问题相关时才注入语气，不再无缘无故说“你喜欢蓝色”。
6. Tool Factory 继续按 intent 动态加载，普通聊天 tools=[]。

安装：
把压缩包内容解压覆盖到 C:\MyAgent。

保留现有：
- qingyuan_stt_server.py
- CosyVoice\qingyuan_tts_server.py
- qingyuan_launcher.py
- qingyuan_tray.py
- start_qingyuan_supervised.bat

建议测试：
1. 在吗
2. 帮我用 Chrome 搜索明日方舟
3. 帮我把微信拉到前台
4. 帮我在微信群聊9652711中发送一句你好
