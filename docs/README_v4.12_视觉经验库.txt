清渊 v4.12：Visual Experience Library
============================================

目录职责：

1. 用户提供的长期参考
   C:\MyAgent\assets\wechat\

   reference_main.png
   layout.json

   用户额外参考图：
   C:\MyAgent\assets\wechat\user_examples\
       search_box\
       search_result\
       chat_header\
       message_box\

   这些内容不会自动删除。

2. 清渊自己积累的微信有效经验
   C:\MyAgent\workspace\wechat_debug\

   search_box\
   search_result\
   chat_header\
   message_box\
   send_success\
   failures\

   只有最终成功任务的关键步骤才会晋升到经验库。
   NO_MATCH 等有分析价值的失败案例可进入 failures。

   每类最多保留：
   WECHAT_EXPERIENCE_MAX_PER_CATEGORY = 12

   重复图片不会重复保存。

3. 普通临时截图 / 工作草稿
   C:\MyAgent\workspace\screenshots\

   所有实时截图、局部截图、scaled 图先进入这里。

   默认：
   TEMP_SCREENSHOT_RETENTION_MINUTES = 30

   启动时清理一次，
   后台每 5 分钟清理一次。

核心原则：

assets
  = 用户教给她的

wechat_debug
  = 她自己总结出的有效经验

screenshots
  = 当前任务的临时草稿
