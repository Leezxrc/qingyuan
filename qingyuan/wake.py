from .config import (
    WAKE_WORD,
    WAKE_FIRST_CHARS,
    WAKE_SECOND_CHARS,
)


# Whisper 在待机低偏置识别下，偶尔会把“清渊”整词漂移成这些词。
# 这些高风险别名不做全句无条件匹配，而是结合“句首/句尾 + 呼叫语境”判断，
# 避免普通句子里的“气晕”等词误唤醒。
NOISY_WAKE_ALIASES = {
    "行员",
    "行員",
    "气晕",
    "氣暈",
}

# “在吗”也经常被 Whisper 漂移。
CALL_CUES = {
    "在吗",
    "在嗎",
    "在嘛",
    "在么",
    "再麻",
    "再馬",
    "再吗",
    "再嗎",
    "在不在",
}

# 当噪声别名出现在句首时，后面跟这些词更像是在叫清渊执行命令。
COMMAND_CUES = (
    "帮我",
    "幫我",
    "帮",
    "幫",
    "能不能",
    "能否",
    "可以",
    "请",
    "請",
    "打开",
    "打開",
    "搜索",
    "搜尋",
    "查看",
    "看看",
    "告诉我",
    "告訴我",
    "在吗",
    "在嗎",
)


def normalize_command(text):
    return str(text).strip().lower()


def _strip_outer_punctuation(text):
    return str(text).strip(
        " \t\r\n，,。！？!?：:；;、"
    )


def _find_contextual_noisy_alias(text):
    """
    处理“清渊 -> 行員 / 氣暈”这类整词漂移。

    规则：
    1. 别名本身单独出现：接受。
    2. 别名在句尾，并且前面出现“在吗/再麻/再馬”等呼叫语境：接受。
    3. 别名在句首，并且后面明显像命令：接受。
    4. 其他情况拒绝，减少普通语句误唤醒。
    """
    normalized = _strip_outer_punctuation(text)

    for alias in NOISY_WAKE_ALIASES:
        index = normalized.find(alias)

        if index == -1:
            continue

        end = index + len(alias)

        # 单独叫名字
        if normalized == alias:
            return index, end

        before = normalized[:index]
        after = normalized[end:]

        # “在吗/再麻 + 清渊(误识别)” 类句尾呼叫
        if end == len(normalized):
            if any(cue in before for cue in CALL_CUES):
                return index, end

        # “清渊(误识别) + 帮我/能否/可以...” 类句首命令
        if index == 0:
            after_clean = after.lstrip(
                " ，,。！？!?：:；;、"
            )

            if any(
                after_clean.startswith(cue)
                for cue in COMMAND_CUES
            ):
                return index, end

    return None


def find_wake_span(text):
    if not text:
        return None

    text = str(text)

    # 1. 真正的“清渊”
    exact = text.find(WAKE_WORD)

    if exact != -1:
        return (
            exact,
            exact + len(WAKE_WORD),
        )

    # 2. 常规两音节近音：
    #    青元 / 请愿 / 清淵 / 青雲 等。
    for i in range(len(text) - 1):
        if (
            text[i] in WAKE_FIRST_CHARS
            and text[i + 1] in WAKE_SECOND_CHARS
        ):
            return i, i + 2

    # 3. Whisper 整词漂移：
    #    行員 / 氣暈 等，仅在明确呼叫语境中接受。
    return _find_contextual_noisy_alias(text)


def strip_wake_word(text):
    normalized = str(text).strip()

    span = find_wake_span(normalized)

    if span is None:
        return False, normalized

    start, end = span

    command = (
        normalized[:start]
        + normalized[end:]
    ).strip(
        " ，,。！？!?：:；;、"
    )

    # 如果剩下的只是“在吗/再麻”等呼叫词，
    # 统一转换成最简单的“在吗”，避免把 Whisper 错字送给主模型。
    compact = command.replace(" ", "")

    if compact in CALL_CUES:
        command = "在吗"

    return True, command


def is_standby_phrase(text):
    command = normalize_command(text)

    exact = {
        "没在说你",
        "没有在说你",
        "不是在说你",
        "我没在说你",
        "我没有在说你",
        "我并没有在说你",
        "我没叫你",
        "我没有叫你",
        "我并没有叫你",
        "我刚刚没有叫你",
        "我刚刚没有再叫你",
        "不是叫你",
        "进入待机",
        "回到待机",
        "休息吧",
        "先休息",
        "先别听我说话",
    }

    if command in exact:
        return True

    fragments = [
        "没在说你",
        "没有在说你",
        "不是在说你",
        "没叫你",
        "没有叫你",
        "并没有叫你",
        "不是叫你",
    ]

    return any(
        fragment in command
        for fragment in fragments
    )
