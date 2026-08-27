import ctypes
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime


class SystemTools:
    def __init__(self, runtime, permission):
        self.runtime = runtime
        self.permission = permission

    def get_current_time(self) -> str:
        """
        读取当前 Windows 本机的日期、星期和时间。

        用于回答现在几点、今天几号、今天星期几等实时问题。
        这是低风险只读系统信息，不需要用户授权。
        """
        now = datetime.now()

        weekdays = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        ]

        return (
            f"当前本机时间是"
            f"{now.year}年{now.month}月{now.day}日，"
            f"{weekdays[now.weekday()]}，"
            f"{now.hour}点{now.minute}分。"
        )


    @staticmethod
    def _path(value):
        return Path(str(value)).expanduser().resolve()

    # ---------------- filesystem read ----------------

    def list_path(self, path: str) -> str:
        """列出任意已授权目录内容。"""
        ok, reason = self.permission.require(
            "file_read",
            path,
        )
        if not ok:
            return reason

        try:
            target = self._path(path)
            if not target.exists():
                return f"路径不存在：{target}"
            if not target.is_dir():
                return f"不是目录：{target}"

            items = []
            for child in target.iterdir():
                kind = "文件夹" if child.is_dir() else "文件"
                items.append(f"[{kind}] {child.name}")

            self.runtime.record_desktop_action(
                "file_read:list"
            )
            return "\n".join(items) if items else "目录为空。"
        except Exception as e:
            return f"列目录失败：{e}"

    def read_text_file(self, path: str) -> str:
        """读取任意已授权文本文件。"""
        ok, reason = self.permission.require(
            "file_read",
            path,
        )
        if not ok:
            return reason

        try:
            target = self._path(path)
            if not target.is_file():
                return f"不是文件：{target}"

            text = target.read_text(
                encoding="utf-8",
            )

            self.runtime.record_desktop_action(
                "file_read:text"
            )

            # 防止一次把巨大文件塞回模型。
            if len(text) > 20000:
                return (
                    text[:20000]
                    + "\n\n[内容过长，仅返回前 20000 字符]"
                )

            return text
        except UnicodeDecodeError:
            return "当前只支持 UTF-8 文本读取。"
        except Exception as e:
            return f"读取失败：{e}"

    # ---------------- filesystem write ----------------

    def write_text_file(
        self,
        path: str,
        content: str,
    ) -> str:
        """创建或覆盖任意已授权文本文件。"""
        ok, reason = self.permission.require(
            "file_write",
            path,
        )
        if not ok:
            return reason

        try:
            target = self._path(path)
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            target.write_text(
                str(content),
                encoding="utf-8",
            )

            self.runtime.record_desktop_action(
                "file_write"
            )
            return f"已写入：{target}"
        except Exception as e:
            return f"写入失败：{e}"

    def create_folder(self, path: str) -> str:
        """创建任意已授权文件夹。"""
        ok, reason = self.permission.require(
            "file_write",
            path,
        )
        if not ok:
            return reason

        try:
            target = self._path(path)
            target.mkdir(
                parents=True,
                exist_ok=True,
            )
            self.runtime.record_desktop_action(
                "file_write:create_folder"
            )
            return f"已创建文件夹：{target}"
        except Exception as e:
            return f"创建失败：{e}"

    def move_path(
        self,
        source: str,
        destination: str,
    ) -> str:
        """移动或重命名已授权路径。"""
        ok1, reason1 = self.permission.require(
            "file_move",
            source,
        )
        ok2, reason2 = self.permission.require(
            "file_move",
            destination,
        )

        if not ok1:
            return reason1
        if not ok2:
            return reason2

        try:
            src = self._path(source)
            dst = self._path(destination)
            dst.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.move(
                str(src),
                str(dst),
            )
            self.runtime.record_desktop_action(
                "file_move"
            )
            return f"已移动：{src} -> {dst}"
        except Exception as e:
            return f"移动失败：{e}"

    def delete_path(self, path: str) -> str:
        """
        删除已授权文件或文件夹。

        注意：这是实际删除能力，因此必须在任务确认中明确包含 file_delete。
        """
        ok, reason = self.permission.require(
            "file_delete",
            path,
        )
        if not ok:
            return reason

        try:
            target = self._path(path)
            if not target.exists():
                return f"路径不存在：{target}"

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

            self.runtime.record_desktop_action(
                "file_delete"
            )
            return f"已删除：{target}"
        except Exception as e:
            return f"删除失败：{e}"

    # ---------------- system power/session ----------------

    def system_power(
        self,
        action: str,
    ) -> str:
        """
        执行固定白名单 Windows 电源/会话动作。

        不接受 shell 命令，不接受额外参数。
        action 只能是：
        shutdown / restart / sleep / lock / logout

        此工具需要：
        1. 当前 Task Permit 含 power_control
        2. 第二次针对具体动作的最终确认
        """
        aliases = {
            "shutdown": "shutdown",
            "关机": "shutdown",
            "关闭电脑": "shutdown",

            "restart": "restart",
            "reboot": "restart",
            "重启": "restart",
            "重新启动": "restart",

            "sleep": "sleep",
            "睡眠": "sleep",
            "休眠": "sleep",

            "lock": "lock",
            "锁屏": "lock",
            "锁定": "lock",
            "锁定电脑": "lock",

            "logout": "logout",
            "logoff": "logout",
            "注销": "logout",
            "退出登录": "logout",
        }

        raw = str(
            action
        ).strip().lower()

        normalized = aliases.get(
            raw
        )

        if normalized is None:
            return (
                "拒绝执行：system_power 只允许 "
                "shutdown / restart / sleep / lock / logout。"
            )

        ok, reason = (
            self.permission.require(
                "power_control",
                normalized,
            )
        )

        if not ok:
            return reason

        labels = {
            "shutdown": "立即关闭这台电脑",
            "restart": "立即重新启动这台电脑",
            "sleep": "让这台电脑进入睡眠",
            "lock": "立即锁定这台电脑",
            "logout": "立即注销当前 Windows 会话",
        }

        final_prompt = (
            f"最终动作：{labels[normalized]}。\n"
            "这是系统级操作，确认后会立即执行。\n"
            "只会执行这一项固定白名单动作。\n"
            "是否确认？"
        )

        if not (
            self.permission
            .voice
            .request_confirmation(
                final_prompt,
                operation_name=(
                    "系统级最终确认"
                ),
            )
        ):
            return (
                "用户取消了系统级最终确认，"
                "未执行任何电源/会话操作。"
            )

        try:
            if normalized == "shutdown":
                executable = (
                    shutil.which(
                        "shutdown.exe"
                    )
                    or str(
                        Path(
                            r"C:\Windows\System32\shutdown.exe"
                        )
                    )
                )

                subprocess.Popen(
                    [
                        executable,
                        "/s",
                        "/t",
                        "0",
                    ],
                    shell=False,
                )

                result = "已提交 Windows 关机指令。"

            elif normalized == "restart":
                executable = (
                    shutil.which(
                        "shutdown.exe"
                    )
                    or str(
                        Path(
                            r"C:\Windows\System32\shutdown.exe"
                        )
                    )
                )

                subprocess.Popen(
                    [
                        executable,
                        "/r",
                        "/t",
                        "0",
                    ],
                    shell=False,
                )

                result = "已提交 Windows 重启指令。"

            elif normalized == "logout":
                executable = (
                    shutil.which(
                        "shutdown.exe"
                    )
                    or str(
                        Path(
                            r"C:\Windows\System32\shutdown.exe"
                        )
                    )
                )

                subprocess.Popen(
                    [
                        executable,
                        "/l",
                    ],
                    shell=False,
                )

                result = "已提交 Windows 注销指令。"

            elif normalized == "lock":
                if not (
                    ctypes.windll
                    .user32
                    .LockWorkStation()
                ):
                    return (
                        "锁屏失败：Windows "
                        "LockWorkStation 返回失败。"
                    )

                result = "已锁定 Windows。"

            elif normalized == "sleep":
                powrprof = (
                    ctypes.WinDLL(
                        "PowrProf.dll"
                    )
                )

                set_suspend = (
                    powrprof
                    .SetSuspendState
                )

                set_suspend.argtypes = [
                    ctypes.c_bool,
                    ctypes.c_bool,
                    ctypes.c_bool,
                ]

                set_suspend.restype = (
                    ctypes.c_bool
                )

                if not set_suspend(
                    False,
                    False,
                    False,
                ):
                    return (
                        "睡眠失败：Windows "
                        "SetSuspendState 返回失败。"
                    )

                result = (
                    "已请求 Windows 进入睡眠。"
                )

            else:
                return (
                    "拒绝执行：未知系统动作。"
                )

            self.runtime.record_desktop_action(
                f"power_control:{normalized}"
            )

            return result

        except Exception as e:
            return (
                "系统电源/会话操作失败："
                f"{type(e).__name__}: {e}"
            )

    # ---------------- open / launch ----------------

    def open_path(self, path: str) -> str:
        """使用 Windows 默认程序打开已授权路径。"""
        # 打开文件/文件夹属于读取+启动外部程序
        allowed = (
            self.permission.has("file_read")
            or self.permission.has("app_launch")
        )

        if not allowed:
            return "当前任务没有获得打开路径所需权限。"

        if not self.permission.target_allowed(path):
            return "拒绝执行：目标超出本次任务已确认范围。"

        try:
            target = self._path(path)
            if not target.exists():
                return f"路径不存在：{target}"

            os.startfile(str(target))
            self.runtime.record_desktop_action(
                "open_path"
            )
            return f"已打开：{target}"
        except Exception as e:
            return f"打开失败：{e}"

    def launch_program(
        self,
        program: str,
        arguments: list = None,
    ) -> str:
        """
        启动用户已授权的程序。

        不通过 shell=True，不执行命令字符串解释。
        program 必须是明确的 exe 路径或 PATH 中可执行程序。
        """
        ok, reason = self.permission.require(
            "app_launch",
            program,
        )
        if not ok:
            return reason

        program = str(program).strip()
        args = [
            str(x)
            for x in (arguments or [])
        ]

        try:
            executable = None

            if Path(program).expanduser().exists():
                executable = str(
                    Path(program).expanduser().resolve()
                )
            else:
                executable = shutil.which(program)

            if not executable:
                return (
                    "没有找到可执行程序："
                    f"{program}。"
                    "可以改用 GUI 在开始菜单中打开。"
                )

            subprocess.Popen(
                [executable, *args],
                shell=False,
            )

            self.runtime.record_desktop_action(
                "app_launch"
            )
            return f"已启动：{executable}"
        except Exception as e:
            return f"启动失败：{e}"
