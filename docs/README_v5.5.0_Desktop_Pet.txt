清渊 v5.5.0 — Desktop Pet Body v1（CODE ONLY）
================================================

定位
----
桌宠只是清渊的“身体 / 表现层”，不承载模型、记忆、RAG、权限或电脑操作逻辑。
清渊的 Brain Backend、Action Host、STT、TTS、Memory 等原架构保持不变。

本版新增
--------
1. 清渊启动后自动启动轻量桌宠窗口。
2. 透明、置顶、无边框窗口，可直接拖动位置。
3. 左键单击桌宠：唤醒清渊，下一轮语音无需再次说“清渊”。
4. 右键菜单：唤醒、开启/暂停麦克风、待机、停止说话、只关闭桌宠。
5. 状态联动：
   - 待机
   - 正在听你说
   - 正在思考
   - 正在执行
   - 正在说话
   - 等待确认
   - 麦克风暂停
   - 未连接
6. TTS 播报开始时同步显示对话气泡。
7. 桌宠状态和气泡仅存在运行时内存，不写入任何持久化存储。
8. 默认使用轻量矢量占位角色；如果存在：
   C:\MyAgent\assets\qingyuan_pet.png
   会优先显示该透明 PNG。

安装
----
1. 完全退出清渊。
2. 将本 ZIP 解压到 C:\MyAgent\ 。
3. 允许覆盖同名 qingyuan/*.py 文件。
4. 重新启动清渊。

数据安全
--------
本升级包不包含、不创建、不覆盖：
- data
- memory
- knowledge
- RAG 数据
- skills 学习数据
- workspace
- STT vocabulary
- 用户视觉学习数据
- 任何长期记忆文件

本版改动文件
------------
qingyuan/desktop_pet.py       新增桌宠表现层
qingyuan/runtime.py           新增运行时气泡文本状态（仅内存）
qingyuan/control.py           新增桌宠状态字段和 /wake
qingyuan/frontend_service.py  自动启动/关闭桌宠
qingyuan/voice.py             TTS 与气泡同步
qingyuan/version.py           v5.5.0 / protocol 8

说明
----
v1 的重点是先把“身体”和现有清渊稳定接通。
后续可继续在表现层升级 Live2D、嘴型同步、眨眼、鼠标视线跟随、情绪与动作，
无需改动清渊的 Brain / Memory 核心。
