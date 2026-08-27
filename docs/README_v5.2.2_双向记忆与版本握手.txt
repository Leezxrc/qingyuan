清渊 v5.2.2
============================================================

本版修复两个独立问题。


一、长期记忆支持双向查询

保存：

家庭群 = 9652711

现在支持正向：

我的家庭群是什么？
我的微信家庭群叫什么？
家庭群是哪个？

直接回答：

家庭群 -> 9652711


也支持反向：

微信群9652711是我的什么群？
9652711是什么群？
9652711对应哪个群？

直接回答：

9652711 -> 家庭群


两种查询：
- 只读本地 data\knowledge
- 不打开微信
- 不申请 Task Permit
- 不调用鼠标/键盘/屏幕


二、Backend 版本握手

之前覆盖新版文件后，
旧 qingyuan_backend.py 进程可能仍占用：

127.0.0.1:8770

Frontend 只判断“在线”，
所以可能继续使用旧代码。

v5.2.2 加入：

QINGYUAN_VERSION = 5.2.2
BACKEND_PROTOCOL_VERSION = 2

Backend /health 返回版本。

Frontend 启动时：

检查 Backend
    ↓
版本一致
    -> 继续

版本不一致
    ↓
自动 /shutdown 旧 Backend
    ↓
等待端口释放
    ↓
启动当前新版 Backend
    ↓
再次验证版本

如果仍然不一致，
Frontend 会明确显示启动失败，
不会再把旧 Backend 当成正常在线。


三、正常启动应该看到

清渊 Frontend v5.2.2 已启动

Backend 状态：在线
Backend 版本：5.2.2


四、测试双向记忆

运行：

C:\MyAgent\.venv\Scripts\python.exe
C:\MyAgent\tools\test_memory_bidirectional.py


五、检查实际正在运行的 Backend

运行：

C:\MyAgent\.venv\Scripts\python.exe
C:\MyAgent\tools\check_backend_version.py

应该看到：

version = 5.2.2
protocol_version = 2


六、如果安装后第一次仍看到旧进程

完全退出清渊。

任务管理器中确认没有：

python.exe / qingyuan_backend.py

然后重新运行：

C:\MyAgent\start_qingyuan_supervised.bat

之后 v5.2.2 会自行进行版本握手。
