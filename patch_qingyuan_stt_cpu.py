from pathlib import Path
import shutil
import py_compile

TARGET = Path(r"C:\MyAgent\qingyuan_voice_core.py")
BACKUP = Path(r"C:\MyAgent\qingyuan_voice_core_before_cpu_stt.py")

if not TARGET.is_file():
    raise SystemExit(f"找不到目标文件：{TARGET}")

text = TARGET.read_text(encoding="utf-8")

if not BACKUP.exists():
    shutil.copy2(TARGET, BACKUP)
    print(f"已备份：{BACKUP}")
else:
    print(f"备份已存在，不覆盖：{BACKUP}")

# 1) 在 FunASR / ModelScope 导入之前彻底隐藏 CUDA。
cuda_guard = (
    '# 清渊 STT 独占 CPU：把 GPU 留给 Ollama / CosyVoice。\n'
    '# 必须在 FunASR / ModelScope（以及它们间接导入 torch）之前设置。\n'
    'os.environ["CUDA_VISIBLE_DEVICES"] = "-1"\n'
)

import_anchor = "import wave\nfrom http.server"
if 'CUDA_VISIBLE_DEVICES' not in text:
    if import_anchor not in text:
        raise SystemExit("未找到 import 插入位置，停止修改。")
    text = text.replace(
        import_anchor,
        "import wave\n\n" + cuda_guard + "\nfrom http.server",
        1,
    )

# 2) SenseVoice 明确走 CPU，并限制 CPU 线程数。
old_sense = (
    '    sensevoice_model = AutoModel(\n'
    '        model=SENSEVOICE_MODEL,\n'
    '        trust_remote_code=True,\n'
    '        disable_update=True,\n'
    '    )\n'
)
new_sense = (
    '    sensevoice_model = AutoModel(\n'
    '        model=SENSEVOICE_MODEL,\n'
    '        trust_remote_code=True,\n'
    '        disable_update=True,\n'
    '        device="cpu",\n'
    '        ncpu=4,\n'
    '    )\n'
)
if old_sense in text:
    text = text.replace(old_sense, new_sense, 1)
elif 'device="cpu"' not in text:
    raise SystemExit("未找到 SenseVoice 加载块，停止修改。")

# 3) CAM++ 明确走 CPU。
old_cam = (
    '        speaker_pipeline = pipeline(\n'
    '            task="speaker-verification",\n'
    '            model=SPEAKER_MODEL,\n'
    '            model_revision=SPEAKER_MODEL_REVISION,\n'
    '        )\n'
)
new_cam = (
    '        speaker_pipeline = pipeline(\n'
    '            task="speaker-verification",\n'
    '            model=SPEAKER_MODEL,\n'
    '            model_revision=SPEAKER_MODEL_REVISION,\n'
    '            device="cpu",\n'
    '        )\n'
)
if old_cam in text:
    text = text.replace(old_cam, new_cam, 1)
elif 'device="cpu"' not in text:
    raise SystemExit("未找到 CAM++ 加载块，停止修改。")

# 4) 启动日志明确标记 CPU 模式。
old_arch = (
    '    print(\n'
    '        "语音架构：WebRTC VAD -> SenseVoiceSmall"\n'
    '        " -> 拼音唤醒 -> CAM++"\n'
    '    )\n'
)
new_arch = old_arch + '    print("STT 推理设备：CPU（GPU 保留给 Ollama / CosyVoice）")\n'
if old_arch in text and "STT 推理设备：CPU" not in text:
    text = text.replace(old_arch, new_arch, 1)

# 5) health 里加一个可检查字段。
health_anchor = '                    "engine": "SenseVoiceSmall",\n'
if health_anchor in text and '"device": "cpu"' not in text:
    text = text.replace(
        health_anchor,
        health_anchor + '                    "device": "cpu",\n',
        1,
    )

TARGET.write_text(text, encoding="utf-8")

try:
    py_compile.compile(str(TARGET), doraise=True)
except Exception:
    shutil.copy2(BACKUP, TARGET)
    raise

print()
print("修改完成：")
print("- SenseVoiceSmall -> CPU")
print("- CAM++ -> CPU")
print("- CUDA 对 STT 进程隐藏")
print("- SenseVoice CPU 线程 -> 4")
print("- 已通过 Python 语法检查")
print()
print("目标：", TARGET)
