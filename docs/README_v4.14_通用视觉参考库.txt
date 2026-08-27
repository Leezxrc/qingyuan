清渊 v4.14：Generic Visual Reference Library
================================================

不再把参考截图系统写死为微信。

用户统一入口：

C:\MyAgent\assets\visual\inbox\

你可以把任何软件完整截图丢进去。

清渊会用视觉模型判断：

- 软件名称
- 软件类型
- search_box
- sidebar
- list_area
- header
- main_content
- input_box
- toolbar
- navigation
- 或该软件特有区域

然后自动保存：

C:\MyAgent\assets\visual\apps\<app_key>\

目录：

originals\
    用户提供的完整原始截图

examples\
    自动裁剪出来的 UI 参考区域

metadata\
    软件识别结果、region bbox、置信度等 JSON

例如：

assets\visual\apps\wechat\
assets\visual\apps\chrome\
assets\visual\apps\file_explorer\
assets\visual\apps\steam\

微信原来的：
C:\MyAgent\assets\wechat\

仍保留兼容，不会自动删除。

新的长期方向是：
assets\visual
作为所有软件统一视觉知识库。

workspace\wechat_debug
仍然是清渊实际执行微信任务后积累的经验。

workspace\screenshots
仍然是临时运行截图。
