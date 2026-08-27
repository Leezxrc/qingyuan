import time
from pathlib import Path

from .config import (
    TASK_CAPABILITIES,
    DESKTOP_TASK_IDLE_TIMEOUT_SECONDS,
)


CAPABILITY_LABELS = {
    "screen_read": "读取当前屏幕",
    "window_read": "读取窗口列表",
    "file_read": "读取文件/目录",
    "window_control": "切换/控制窗口",
    "mouse": "鼠标点击",
    "keyboard": "键盘输入",
    "scroll": "页面滚动",
    "app_launch": "启动程序",
    "power_control": "系统电源/会话控制",
    "file_write": "创建/修改文件",
    "file_move": "移动/重命名文件",
    "file_delete": "删除文件/文件夹",
}


class TaskPermissionBroker:
    """
    一次用户任务 = 一张临时许可证。

    关键约束：
    - task_description 永远取用户原始命令，不由 LLM 自由改写。
    - 没有明确确认，任何受控能力都不可使用。
    - 许可证只包含本次确认的 capabilities + targets。
    - 任务结束、超时或 clear 后立即失效。
    """

    def __init__(self, runtime, voice):
        self.runtime = runtime
        self.voice = voice

    def begin_request(self, user_request):
        with self.runtime.desktop_lock:
            self.runtime.desktop_task["original_request"] = (
                str(user_request).strip()
            )

    def original_request(self):
        with self.runtime.desktop_lock:
            return str(
                self.runtime.desktop_task.get(
                    "original_request",
                    "",
                )
            )

    def _normalize_targets(self, targets):
        if targets is None:
            return []
        if isinstance(targets, str):
            targets = [targets]
        result = []
        for item in targets:
            item = str(item).strip()
            if item and item not in result:
                result.append(item)
        return result[:20]

    def authorize_task(
        self,
        capabilities: list,
        targets: list = None,
    ) -> str:
        """
        为当前用户原始命令申请一次任务许可证。

        capabilities:
            screen_read / window_read / file_read /
            window_control / mouse / keyboard / scroll /
            app_launch / power_control /
            file_write / file_move / file_delete

        targets:
            本次允许操作的程序、窗口、路径或对象。
        """
        request = self.original_request()

        if not request:
            return "当前没有可授权的用户任务。"

        requested = {
            str(x).strip().lower()
            for x in (capabilities or [])
        }

        invalid = requested - TASK_CAPABILITIES
        if invalid:
            return (
                "包含未开放的能力："
                + "、".join(sorted(invalid))
            )

        if not requested:
            return "没有申请任何任务能力。"

        targets = self._normalize_targets(targets)

        labels = [
            CAPABILITY_LABELS.get(x, x)
            for x in sorted(requested)
        ]

        prompt = (
            f"你的原始命令：{request}\n"
            f"本次申请权限：{'、'.join(labels)}\n"
            f"本次目标：{'、'.join(targets) if targets else '仅限原始命令明确对象'}\n"
            "是否允许执行这个任务？"
        )

        if not self.voice.request_confirmation(
            prompt,
            operation_name="执行当前任务",
        ):
            self.runtime.clear_desktop_task(
                preserve_request=True
            )
            return "用户拒绝了本次任务授权。"

        with self.runtime.desktop_lock:
            self.runtime.desktop_task.update({
                "active": True,
                "description": request,
                "capabilities": requested,
                "targets": targets,
                "last_activity": time.monotonic(),
                "action_count": 0,
                "action_types": set(),
            })

        self.runtime.mark_activity(
            "authorize_task"
        )

        return (
            "任务许可证已生效。"
            f"原始命令：{request}；"
            f"能力：{', '.join(sorted(requested))}；"
            f"目标：{targets or ['原始命令明确对象']}。"
        )

    def has(self, capability):
        if not self.runtime.desktop_task_is_active():
            return False

        with self.runtime.desktop_lock:
            return (
                capability
                in self.runtime.desktop_task["capabilities"]
            )

    def targets(self):
        if not self.runtime.desktop_task_is_active():
            return []

        with self.runtime.desktop_lock:
            return list(
                self.runtime.desktop_task.get(
                    "targets",
                    [],
                )
            )

    def target_allowed(self, value):
        """
        targets 为空时，不额外做字符串级 scope 限制；
        targets 非空时，目标必须与其中至少一个 scope 相关。

        路径按 prefix 判断；窗口/程序按包含关系判断。
        """
        targets = self.targets()

        if not targets:
            return True

        value = str(value).strip()
        if not value:
            return False

        value_lower = value.lower()

        for target in targets:
            target = str(target).strip()
            if not target:
                continue

            # 尝试路径 scope
            try:
                value_path = Path(value).expanduser().resolve()
                target_path = Path(target).expanduser().resolve()

                if (
                    value_path == target_path
                    or target_path in value_path.parents
                ):
                    return True
            except Exception:
                pass

            target_lower = target.lower()

            if (
                target_lower in value_lower
                or value_lower in target_lower
            ):
                return True

        return False

    def require(self, capability, target=None):
        if not self.has(capability):
            return (
                False,
                f"当前任务没有获得 {capability} 权限。"
            )

        if target is not None and not self.target_allowed(target):
            return (
                False,
                "拒绝执行：目标超出本次任务已确认范围。"
            )

        return True, ""

    def end_task(self):
        if not self.runtime.desktop_task_is_active():
            return "当前没有有效任务许可证。"

        with self.runtime.desktop_lock:
            description = self.runtime.desktop_task["description"]

        self.runtime.clear_desktop_task(
            preserve_request=True
        )

        return (
            f"任务已结束并收回全部临时权限：{description}"
        )
