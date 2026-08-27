清渊 v5.4.0 — STT Accuracy Phase 1
===================================

类型：CODE ONLY 代码升级包
Backend Protocol：保持 8，不变

本次目标
--------
在不强制更换 Whisper 模型、不提高默认硬件要求的情况下，先提升当前语音识别链路的稳定性和准确率。

主要改动
--------
1. 句首保护
   - PRE_ROLL 从 0.30 秒提高到 0.55 秒。
   - 减少“清渊”或句首第一个词被截掉的概率。

2. 避免双重 VAD 截字
   - 录音层已经完成声音检测与切句。
   - Whisper 转录阶段关闭第二次 vad_filter，避免短词、句首再次被裁剪。

3. 动态 Hotwords
   - 不再只给 Whisper 一个“清渊”热词。
   - 会读取现有 C:\MyAgent\data\stt_vocabulary.json 中的 canonical 词，动态送给 Whisper。
   - 本升级包不会覆盖、重置或替换该词库文件。

4. 短命令自动二次识别
   - 大部分短命令（14 字以内）会进行一次更强 beam 解码复核。
   - 常见极短确认词（在吗/好的/可以/同意/取消/停止/谢谢）不会因此额外变慢。

5. 低置信度自动复核
   - 第一遍识别置信度较低时自动进行第二遍识别。
   - 两个候选根据 Whisper 自身 logprob / no_speech_prob / 完整度 / 用户专有词命中情况综合选择。

6. 待机唤醒双确认修正
   - 第一遍仅轻提示“清渊”可能出现，不强制 hotword。
   - 第二遍才使用动态 hotwords 做确认。
   - 第二遍未确认到唤醒词时返回空结果，避免第一遍误识别直接把 Agent 唤醒。

7. 近期对话轻上下文
   - 仅保留最近 3 条转录作为很短的识别参考。
   - 不写入磁盘，不属于长期记忆，STT 服务重启后自动清空。

8. 模型可配置
   默认仍保持：
       small / cpu / int8
   因此不会突然提高当前电脑负载。

   以后若使用 NVIDIA GPU，可通过环境变量测试：
       QINGYUAN_STT_MODEL=turbo
       QINGYUAN_STT_DEVICE=cuda
       QINGYUAN_STT_COMPUTE_TYPE=float16

   本次升级不会自动下载或切换大模型。

安装
----
1. 完全退出清渊。
2. 将本 ZIP 解压到 C:\MyAgent。
3. 允许覆盖同名代码文件。
4. 重新启动清渊。

建议测试语句
------------
- 清渊，在吗
- 清渊，现在几点了
- 清渊，请问雨伞的英文是什么
- 清渊，帮我打开网易云音乐
- 清渊，明日方舟今天有什么活动
- 清渊，打开 Chrome

观察终端中的：
- 待机第一遍识别
- 待机第二遍确认
- 识别置信度不足，正在自动二次识别……
- 识别候选评分
- 最终识别结果

数据安全
--------
本包不包含、不覆盖：
- data
- memory
- knowledge
- RAG 数据
- skills 学习数据
- workspace
- stt_vocabulary.json
- 视觉学习数据
- 用户长期记忆

本次只包含：
- qingyuan_stt_server.py
- qingyuan/version.py
- docs/README_v5.4.0_STT_Accuracy.txt
