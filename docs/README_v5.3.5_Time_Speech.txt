清渊 v5.3.5 时间播报优化（CODE ONLY）

本补丁基于 v5.3.4 时间系统信息能力继续优化。

改动：
1. get_current_time 默认返回自然中文时间格式：xx点xx分。
2. 普通“现在几点”不主动播报秒数，降低数字串被模型/TTS误读的概率。
3. system_info 提示明确要求沿用工具时间结果，不重新改写数字。
4. QINGYUAN_VERSION 更新到 5.3.5。
5. BACKEND_PROTOCOL_VERSION 保持 8，不改变前后端协议。

安装：
1. 完全退出清渊。
2. 将本压缩包内容解压到 C:\MyAgent\ ，覆盖同名文件。
3. 重新启动清渊。
4. 测试：“清渊，现在几点了？”

重要：
本包仅包含代码与说明，不包含、不覆盖、不迁移任何用户持久化数据。
不包含 data / memory / knowledge / RAG 数据 / skills 学习数据 / workspace / STT 词库 / 视觉学习资料。
