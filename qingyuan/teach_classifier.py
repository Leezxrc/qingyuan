import re


class TeachExecuteClassifier:
    """
    在 Router 之前先判断：
    - execute: 现在就要执行
    - teach: 用户在教规则/纠正做法/定义经验
    - normal: 普通问答

    这里只做意图分类，不执行任何工具。
    """

    TEACH_PATTERNS = [
        r"以后.*不要",
        r"以后.*要",
        r"以后.*默认",
        r"记住.*以后",
        r"记住.*的时候",
        r".*的时候不要",
        r".*的时候要",
        r".*默认是",
        r".*默认用",
        r"不要再.*",
        r"以后改成",
        r"以后都",
        r"以后统一",
        r"不包括在.*名字",
        r"名字里不要",
        r"搜索时不要",
        r"搜索的时候不要",
        r"我教你",
        r"你要记住",
        r"纠正一下",
        r"不是.*而是",
    ]

    EXECUTE_CUES = [
        "现在",
        "帮我",
        "给我",
        "替我",
        "打开",
        "发送",
        "发一句",
        "发一条",
        "点击",
        "输入",
        "搜索",
        "切换",
        "启动",
        "运行",
        "删除",
        "移动",
        "创建",
    ]

    TEACH_CUES = [
        "以后",
        "记住",
        "默认",
        "不要",
        "规则",
        "经验",
        "习惯",
        "做法",
        "应该",
        "不包括",
        "名字里",
        "搜索的时候",
        "搜索时",
        "我教你",
        "纠正",
    ]

    def classify(
        self,
        text,
    ):
        raw = str(text).strip()

        for pattern in self.TEACH_PATTERNS:
            if re.search(
                pattern,
                raw,
            ):
                return "teach"

        teach_score = sum(
            1
            for cue in self.TEACH_CUES
            if cue in raw
        )

        execute_score = sum(
            1
            for cue in self.EXECUTE_CUES
            if cue in raw
        )

        # “搜索的时候不要……”这类句子虽然含“搜索”，
        # 但明显是在描述规则，不是执行。
        if teach_score >= 2:
            return "teach"

        if (
            execute_score >= 1
            and teach_score == 0
        ):
            return "execute"

        return "normal"
