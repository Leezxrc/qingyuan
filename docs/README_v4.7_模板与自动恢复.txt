清渊 v4.7
==================================

微信视觉正式模板化：
C:\MyAgent\assets\wechat\reference_main.png
C:\MyAgent\assets\wechat\layout.json

搜索框、搜索结果、聊天标题、消息输入框
均优先按 layout.json 的相对区域裁剪，
VLM 只在局部区域内识别。

reference_main.png 只用于布局参考，
当前内容判断仍以实时截图为准。

新增 Replanner：
- 窗口失焦 -> 恢复同一授权窗口
- 视觉定位失败 -> 重新截图并定位
- 浏览器失败 -> 优先回退到确定性新标签搜索
- 每种失败最多自动恢复 2 次
- 不允许扩大原任务、目标或 capability

Agent Core：
Planner
  ↓
Task Permit
  ↓
Executor
  ↓
Replanner
  ↓
Verifier
