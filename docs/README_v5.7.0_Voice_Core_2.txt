清渊 v5.7.0 — Voice Core 2.0（第一阶段）
============================================================

目标
----
把“听见声音”升级成更适合常驻本地智能体的实时语音入口：
WebRTC VAD + 拼音模糊唤醒 + SenseVoice 中文主识别 + Whisper fallback。

本包为 CODE ONLY，不包含、迁移或覆盖：
- data / memory / knowledge
- RAG 数据
- learned skills
- workspace
- stt_vocabulary.json
- 任何用户长期记忆

本次改动
--------
1. WebRTC VAD
   - 20ms 音频帧实时人声检测
   - 保留 0.60 秒 pre-roll，减少句首“清渊”被吞
   - 停顿约 1.10 秒自动结束
   - 如果未安装 webrtcvad，会自动回退旧 RMS 检测

2. 拼音唤醒
   - “清渊 / 青云 / 情愿 / 请元”等近音不再只靠具体汉字
   - 使用 pypinyin + 模糊匹配
   - 保留原字符近音规则作为 fallback

3. SenseVoice + Whisper 双引擎
   - SenseVoiceSmall 可作为中文主识别
   - faster-whisper 继续保留，绝不直接删除
   - SenseVoice 不可用、加载失败或结果可疑时自动回退 Whisper
   - 短命令可用 Whisper 复核专有词

4. 非阻塞 SenseVoice 初始化
   - STT /health 与 Whisper fallback 先可用
   - SenseVoice 在后台加载/首次下载
   - 避免一键 Launcher 因首次模型下载而错误超时

5. 原接口保持兼容
   /listen
   /listen?standby=1
   /listen?barge=1
   /cancel
   /shutdown
   /health

安装
----
A. 完全退出清渊。
B. 将本 ZIP 解压覆盖到 C:\MyAgent。
C. 两种安装方式任选其一：
   完整版（WebRTC VAD + 拼音 + SenseVoice）：
   C:\MyAgent\tools\install_voice_core2_deps.bat

   轻量版（只装 WebRTC VAD + 拼音，继续用 Whisper）：
   C:\MyAgent\tools\install_voice_core2_light_deps.bat
D. 重启 Qingyuan.exe。

如果你暂时不运行依赖安装脚本：
清渊仍会使用现有 faster-whisper，STT 不会因为缺少 SenseVoice 而无法启动。

检查
----
双击：
C:\MyAgent\tools\check_voice_core2.bat

/health 新增字段示例：
{
  "engine": "sensevoice+whisper",
  "sensevoice_state": "ready",
  "webrtc_vad": true,
  "pinyin_wake": true
}

sensevoice_state 可能为：
- pending / loading：后台加载中
- ready：已启用
- missing_dependency：未安装 FunASR
- error：SenseVoice 加载失败，仍使用 Whisper
- disabled：显式设为 Whisper-only

高级切换（可选环境变量）
----------------------
QINGYUAN_ASR_ENGINE=auto       默认，SenseVoice 可用就启用
QINGYUAN_ASR_ENGINE=whisper    强制 Whisper-only
QINGYUAN_SENSEVOICE_DEVICE=cpu 默认 CPU

参考设计
--------
本阶段参考 ABexit/ASR-LLM-TTS 中 WebRTC VAD、SenseVoice 与拼音 KWS
的组合思路，但保持清渊现有 Brain / TTS / Frontend / Action Host 架构。

后续阶段
--------
- CAM++ 主人声纹（敏感动作身份门）
- 回声抑制 / 更可靠的 barge-in
- 独立 Wake Word Engine
- 多语种自动检测
- ASR benchmark / 错词数据闭环
