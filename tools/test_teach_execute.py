from qingyuan.teach_classifier import (
    TeachExecuteClassifier,
)


classifier = (
    TeachExecuteClassifier()
)

tests = [
    "搜索的时候不要加上微信群，微信群默认是微信的群聊不包括在名字内",
    "以后搜索微信群的时候只搜索群名字",
    "现在在我的家庭群里发一句测试1",
    "帮我在微信里搜索9652711",
    "记住家庭群是微信群9652711",
]

for text in tests:
    print(
        classifier.classify(
            text
        ),
        "=>",
        text,
    )
