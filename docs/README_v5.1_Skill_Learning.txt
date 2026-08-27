清渊 v5.1：Skill Learning
============================================================

一、目标

清渊开始从“真实成功任务”中学习可复用流程。

不是：
    成功一次 -> 永久自动执行

而是：
    成功任务
      ↓
    提炼候选 Skill
      ↓
    第二次同类流程再次成功
      ↓
    晋升 learned Skill


二、目录

内置技能：
C:\MyAgent\skills\builtin\

用户手动技能：
C:\MyAgent\skills\user\

自动学习候选：
C:\MyAgent\skills\candidates\

自动学习长期技能：
C:\MyAgent\skills\learned\


三、学习内容

会学习：
- 稳定操作顺序
- 参数位置
- 验证方式
- 原任务已经使用过的 capability 名称

不会学习：
- 具体消息内容
- 具体一次性群号
- 一次性搜索词
- 一次性文件名
- 自动授权
- 绕过 Task Permit


四、安全规则

Skill Learning 不改变权限架构。

用户命令
   ↓
Skill 匹配
   ↓
Planner / Critic
   ↓
Task Permit
   ↓
Executor

learned Skill 也必须重新申请当前任务权限。


五、为什么要求至少成功两次

单次成功可能只是偶然。

所以：

第一次成功
  -> candidates

第二次相似成功
  -> learned

避免把偶然路径当成长期操作习惯。


六、查看技能

可以运行：

C:\MyAgent\.venv\Scripts\python.exe
C:\MyAgent\tools\show_skills.py


七、当前推荐测试

连续完成两次同类型操作，例如：

第一次：
在家庭群里发送“测试一”

第二次：
在家庭群里发送“测试二”

两次都必须真实成功并通过 Verifier。

然后查看：

C:\MyAgent\skills\candidates\
C:\MyAgent\skills\learned\

注意：
如果该流程已经有 builtin skill，
learned skill 仍可能形成，但它代表清渊根据实际执行
积累出的本机经验。
