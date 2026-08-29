import re


class IntentRouter:
    """
    轻量规则路由：
    只负责决定加载哪组工具，不负责判断“能不能做”。
    """

    ACTION_INTENTS = {
        "coding",
        "filesystem",
        "app_launch",
        "foreground",
        "browser_search",
        "wechat_send",
        "system_power",
        "gui",
    }


    TOOL_REQUIRED_INTENTS = {
        "system_info",
    }


    def route(self, text):
        q = str(text).strip().lower()

        # --------------------------------------------------
        # read-only system information
        # --------------------------------------------------
        #
        # 当前只包含时间 / 日期。
        # system_info 是只读能力，不属于 ACTION_INTENTS，
        # 因此不会触发任务授权。
        time_phrases = [
            "现在几点",
            "几点了",
            "当前时间",
            "现在时间",
            "现在是什么时间",
            "现在几点钟",
            "现在几时",
            "今天几号",
            "今天多少号",
            "今天几月几号",
            "今天星期几",
            "今天周几",
            "今天礼拜几",
            "当前日期",
            "今天日期",
            "现在是什么日期",
        ]

        if any(
            phrase in q
            for phrase in time_phrases
        ):
            return "system_info"

        # --------------------------------------------------
        # guarded coding / self-development
        # --------------------------------------------------
        # 只在用户明确要求“修改/实现/修复项目代码”时进入 coding。
        # 单纯问“这段代码是什么意思/帮我写个示例”仍属于 chat。
        coding_action_phrases = [
            "修改代码",
            "改代码",
            "修复代码",
            "修代码",
            "修复bug",
            "修 bug",
            "修bug",
            "改bug",
            "写入项目",
            "写进项目",
            "在项目里实现",
            "在项目中实现",
            "实现到项目",
            "给自己增加",
            "给自己加",
            "给清渊增加",
            "给清渊加",
            "给你自己增加",
            "给你自己加",
            "升级自己",
            "修改清渊",
            "改清渊",
            "修复清渊",
            "检查项目代码",
            "检查你的代码",
            "检查你自己的代码",
            "检查清渊代码",
            "只检查代码",
            "检查代码并修复",
            "运行代码测试",
            "跑代码测试",
            "跑测试并修",
            "重构项目",
            "重构代码",
        ]

        coding_nouns = [
            "代码",
            "源码",
            "项目",
            "仓库",
            "repo",
            "repository",
            "模块",
            "脚本",
        ]

        coding_verbs = [
            "修改",
            "改",
            "修复",
            "实现",
            "重构",
            "增加功能",
            "添加功能",
            "加入功能",
            "写入",
            "保存到",
            "测试并修复",
        ]

        self_coding = (
            any(x in q for x in [
                "清渊",
                "你自己",
                "你的代码",
                "你的项目",
                "自己",
                "myagent",
            ])
            and any(x in q for x in coding_verbs)
        )

        explicit_coding = any(
            phrase in q
            for phrase in coding_action_phrases
        )

        project_coding = (
            any(x in q for x in coding_nouns)
            and any(x in q for x in coding_verbs)
            and any(x in q for x in [
                "文件",
                "目录",
                "路径",
                "c:\\",
                "workspace",
                "工作区",
                "git",
                "github",
                "项目",
                "仓库",
            ])
        )

        if (
            explicit_coding
            or self_coding
            or project_coding
        ):
            return "coding"

        # memory
        #
        # 记忆查询优先于“微信/文件”等 GUI 关键词。
        # “我的微信家庭群叫什么”是读记忆，不是操作微信。
        memory_words = [
            "记住",
            "记一下",
            "以后记得",
            "长期记忆",
            "忘掉",
            "忘记",
            "不要再记",
            "你记得我什么",
            "我让你记住",
            "改成",
            "修改成",
            "叫什么",
            "叫啥",
            "名字是什么",
            "名称是什么",
            "你还记得",
            "还记得",
            "什么群",
            "哪个群",
            "对应什么",
            "对应哪个",
        ]

        relation_query = any(
            x in q
            for x in [
                "是什么",
                "是哪个",
                "是哪一个",
            ]
        ) and any(
            x in q
            for x in [
                "群",
                "目录",
                "路径",
                "浏览器",
                "软件",
                "默认",
                "记忆",
            ]
        )

        if (
            any(
                x in q
                for x in memory_words
            )
            or relation_query
        ):
            return "memory"

        # dedicated Windows power/session control
        power_phrases = [
            "关机",
            "关闭电脑",
            "把电脑关掉",
            "重启电脑",
            "重新启动电脑",
            "重启",
            "睡眠",
            "让电脑睡眠",
            "锁屏",
            "锁定电脑",
            "注销",
            "退出登录",
        ]

        if any(
            phrase in q
            for phrase in power_phrases
        ):
            return "system_power"

        # dedicated WeChat sending
        is_wechat = any(
            x in q
            for x in [
                "微信",
                "微信群",
                "微信群聊",
                "微信群条",
            ]
        )

        wants_send = any(
            x in q
            for x in [
                "发送",
                "发一句",
                "发一条",
                "发消息",
                "帮我发",
                "替我发",
                "说一句",
            ]
        )

        if is_wechat and wants_send:
            return "wechat_send"

        # browser search
        browser = any(
            x in q
            for x in [
                "chrome",
                "谷歌浏览器",
                "浏览器",
                "楼览器",
                "瀏覽器",
                "游览器",
                "浏揽器",
            ]
        )

        search = any(
            x in q
            for x in [
                "搜索",
                "搜一下",
                "搜一搜",
                "查一下",
            ]
        )

        if browser and search:
            return "browser_search"

        if search and any(
            x in q
            for x in [
                "浏览",
                "樓覽",
                "楼览",
                "瀏覽",
                "游览",
            ]
        ):
            return "browser_search"

        # foreground/window switching
        if any(
            x in q
            for x in [
                "拉到前台",
                "切到前台",
                "放到前台",
                "调到前台",
                "調到前台",
                "调到最前",
                "調到最前",
                "拉到最前",
                "放到前面",
                "聚焦",
                "切过去",
                "切過去",
                "调出来",
                "調出來",
            ]
        ):
            return "foreground"

        # filesystem
        if any(
            x in q
            for x in [
                "workspace",
                "工作区",
                "文件",
                "文件夹",
                "目录",
                "路径",
                "桌面",
                "下载",
                "documents",
                "downloads",
                "desktop",
            ]
        ):
            if any(
                x in q
                for x in [
                    "读取",
                    "读一下",
                    "写入",
                    "创建",
                    "保存",
                    "打开",
                    "列出",
                    "查看",
                ]
            ):
                return "filesystem"

        # program launch
        if any(
            x in q
            for x in [
                "打开程序",
                "启动",
                "运行",
                "打开微信",
                "打开chrome",
                "打开 chrome",
                "打开软件",
            ]
        ):
            return "app_launch"

        # generic GUI operation
        gui_action_words = [
            "微信",
            "qq",
            "discord",
            "点击",
            "按一下",
            "选择",
            "进入",
            "发送",
            "输入",
            "滚动",
            "切换",
            "打开页面",
            "打开菜单",
            "关闭菜单",
            "窗口",
            "前台",
            "屏幕",
            "截图",
            "帮我在",
            "帮我用",
        ]

        if any(
            x in q
            for x in gui_action_words
        ):
            return "gui"

        return "chat"

    def is_action_intent(self, intent):
        return intent in self.ACTION_INTENTS

    def requires_tool(self, intent):
        return (
            intent in self.ACTION_INTENTS
            or intent in self.TOOL_REQUIRED_INTENTS
        )