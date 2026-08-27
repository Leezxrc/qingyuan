清渊 v3.1 修复
============================

修复 1：浏览器/微信“明明确认了但还是没权限”
原因：
v3 的 generic authorize_task 只发放 capability，
但 browser_search_new_tab / 微信 GUI 还要求绑定具体 Windows HWND。

现在：
窗口类任务统一使用 authorize_desktop_task。
它内部仍走 Task Permit，但确认后会额外绑定真实目标窗口。

Chrome 搜索：
authorize_desktop_task(Chrome, focus+keyboard)
→ browser_search_new_tab
→ end_desktop_task

微信发送：
authorize_desktop_task(微信, focus+mouse+keyboard+screen)
→ wechat_send_message
→ end_desktop_task


修复 2：清渊把自己说的话识别成用户语音
原因：
音箱 TTS 被麦克风重新拾取。

现在：
- 保存最近一次 TTS 文本和结束时间；
- TTS 结束 3 秒内，如果 STT 文本与刚才 TTS 高度相似，
  自动打印 [自回声忽略] 并丢弃；
- 不会送入主模型。

安装：
把压缩包内内容覆盖到 C:\MyAgent。
