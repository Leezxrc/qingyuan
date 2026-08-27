清渊 v4.5：微信截图定位
==================================

微信 GUI 视觉定位增强：

1. 每个关键步骤自动保存微信窗口截图：
   C:\MyAgent\workspace\wechat_debug\

2. 截图只包含当前授权微信窗口。

3. VLM 定位优先返回 bbox：
   {"bbox":[x1,y1,x2,y2]}

4. 同时兼容：
   - 真实像素坐标
   - 0~1000 归一化坐标

5. 若 VLM 返回归一化坐标，不再直接报“超出分析图范围”，
   会自动换算为实际截图坐标。

6. 独立微信截图测试脚本：
   C:\MyAgent\tools\capture_wechat_window.py

   运行：
   cd C:\MyAgent
   .\.venv\Scripts\python.exe tools\capture_wechat_window.py

   输出：
   C:\MyAgent\workspace\wechat_debug\manual_wechat_capture.png
