清渊 v4.13
====================================

用户不再需要手动分类参考截图。

以后只需要把完整微信窗口截图放到：

C:\MyAgent\assets\wechat\inbox\

文件名任意。

清渊会在：
- 启动时
- 运行期间每 30 秒

自动扫描新截图。

处理流程：

完整截图
  ↓
永久归档到：
C:\MyAgent\assets\wechat\originals\
  ↓
读取 layout.json
  ↓
自动裁剪：
- search_box
- search_result
- chat_header
- message_box
  ↓
自动分类到：
C:\MyAgent\assets\wechat\user_examples\...

状态文件：
C:\MyAgent\assets\wechat\inbox_state.json

同一张未修改截图不会重复处理。

目录原则：

assets\wechat\inbox
= 用户扔完整截图的入口

assets\wechat\originals
= 用户原始完整截图，永久保存

assets\wechat\user_examples
= 自动分类后的用户参考图

workspace\wechat_debug
= 清渊自己成功任务积累的经验

workspace\screenshots
= 临时工作截图，30 分钟清理
