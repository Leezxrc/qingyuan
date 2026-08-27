清渊 v4.11
==================================

微信运行截图改为临时文件。

目录：
C:\MyAgent\workspace\wechat_debug\

默认保留：
30 分钟

自动清理机制：
1. 清渊启动时清理一次过期截图
2. 后台每 5 分钟检查一次
3. 每次微信新截图前也会顺手清理
4. 只删除 wechat_debug 目录中的图片文件
5. 不删除 reference_main.png
   因为参考图位于：
   C:\MyAgent\assets\wechat\reference_main.png

修改保留时间：
C:\MyAgent\qingyuan\config.py

WECHAT_DEBUG_RETENTION_MINUTES = 30

例如：
10  = 保留 10 分钟
60  = 保留 1 小时
1440 = 保留 24 小时
