清渊 v4.15
================================================

视觉系统正式统一。

以后所有软件统一使用：

C:\MyAgent\assets\visual\apps\<app_key>\

每个软件：

profile.json
originals\
examples\
metadata\

微信现在使用：

C:\MyAgent\assets\visual\apps\wechat\

其中：

profile.json
= 微信 UI 稳定区域定义

originals\
= 用户给的完整微信参考截图

examples\
= 自动裁剪 / 用户参考 UI 区域

metadata\
= 视觉分析元数据


旧目录：

C:\MyAgent\assets\wechat\

启动 v4.15 后，清渊会自动迁移：

layout.json
    -> assets\visual\apps\wechat\profile.json

reference_main.png
    -> assets\visual\apps\wechat\originals\reference_main.png

user_examples
    -> assets\visual\apps\wechat\examples


重要：

清渊不会自动删除旧 assets\wechat，
防止迁移过程中误删资料。

确认下面存在后：

C:\MyAgent\assets\visual\apps\wechat\profile.json
C:\MyAgent\assets\visual\apps\wechat\originals\reference_main.png

即可手动整个删除：

C:\MyAgent\assets\wechat\


以后你给任何软件的完整截图，统一只放：

C:\MyAgent\assets\visual\inbox\

不再需要 assets\wechat。
