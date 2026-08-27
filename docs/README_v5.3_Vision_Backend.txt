清渊 v5.3：Vision Backend
============================================================

这一版开始把视觉推理真正放到 Brain Backend。

旧结构：

Windows VisionService
    ↓
Windows Ollama
    ↓
qwen3-vl
    ↓
坐标
    ↓
Windows 点击


v5.3：

Windows
    ↓
只负责截图
    ↓
HTTP IPC + Token
    ↓
Brain Backend /vision/infer
    ↓
qwen3-vl
    ↓
返回视觉判断 / bbox
    ↓
Windows 将 bbox 映射回真实屏幕
    ↓
Task Permit 允许后执行鼠标动作


重要：

Windows 仍然负责：
- 截图权限
- 当前授权窗口
- 屏幕坐标映射
- 鼠标点击
- Task Permit
- 最终安全边界

Brain Backend 只负责：
- 看图
- 判断
- 返回结果

Brain Backend 不能直接点击电脑。


图片传输：

Frontend 会把截图编码为 base64，
发送给：

POST
/vision/infer

因此以后 Backend 放到另一台机器时，
不依赖两台电脑共享同一个截图路径。


显存：

视觉推理前 Backend 会尝试释放：
qwen3:4b-instruct
qwen3:8b

然后运行：
qwen3-vl:4b-instruct

视觉结束后立即卸载 qwen3-vl。

适合当前 RTX 3080 10GB 的显存策略。


微信兼容：

微信专用：
locate_in_image_region
analyze_image_region

也已经走 Backend Vision。

所以：
搜索结果识别
聊天标题确认
输入框识别
通用 GUI 定位

都不再由 Frontend 本地直接调用视觉模型。


版本：
Frontend / Backend 5.3.0
Protocol 4


正常启动应看到：

Frontend v5.3.0
Backend 版本：5.3.0

Backend /health 中：
vision_backend = true
