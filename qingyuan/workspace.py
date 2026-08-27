import os

from .config import WORKSPACE, ALLOWED_APPS


class WorkspaceTools:
    def __init__(self, runtime, voice, window_lookup):
        self.runtime = runtime
        self.voice = voice
        self.window_lookup = window_lookup

    def _safe_path(self, relative_path):
        target = (WORKSPACE / relative_path).resolve()
        try:
            target.relative_to(WORKSPACE)
        except ValueError:
            raise PermissionError("拒绝访问：路径位于 workspace 之外。")
        return target

    def list_files(self) -> str:
        """列出 workspace 内文件和文件夹。"""
        items = []
        for path in WORKSPACE.rglob("*"):
            rel = path.relative_to(WORKSPACE)
            items.append(
                f"[文件夹] {rel}" if path.is_dir() else f"[文件] {rel}"
            )
        return "\n".join(items) if items else "workspace 当前为空。"

    def read_file(self, relative_path: str) -> str:
        """读取 workspace 内 UTF-8 文本文件。"""
        try:
            path = self._safe_path(relative_path)
            if not path.exists():
                return f"文件不存在：{relative_path}"
            if not path.is_file():
                return f"这不是文件：{relative_path}"
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "目前只支持读取 UTF-8 文本文件。"
        except Exception as e:
            return f"读取失败：{e}"

    def write_file(self, relative_path: str, content: str) -> str:
        """写入 workspace 文本文件；会请求确认。"""
        try:
            path = self._safe_path(relative_path)
            print(f"\n【清渊请求写入文件】\n目标：{path}")
            if not self.voice.request_confirmation(
                "允许这次写入吗？",
                operation_name="写入文件",
            ):
                return "用户拒绝了这次写入操作。"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")
            self.runtime.mark_activity("write_file")
            return f"已成功写入：{relative_path}"
        except Exception as e:
            return f"写入失败：{e}"

    def open_workspace_path(self, relative_path: str = ".") -> str:
        """打开 workspace 内文件或文件夹；会请求确认。"""
        try:
            path = self._safe_path(relative_path)
            if not path.exists():
                return f"不存在：{relative_path}"
            if not self.voice.request_confirmation(
                f"打开：{path}\n允许吗？",
                operation_name="打开文件或文件夹",
            ):
                return "用户拒绝了打开操作。"
            os.startfile(str(path))
            self.runtime.mark_activity("open_workspace_path")
            return f"已打开：{relative_path}"
        except Exception as e:
            return f"打开失败：{e}"

    def open_app(self, app_name: str) -> str:
        """旧兼容启动工具；新任务优先使用 launch_program。"""
        import subprocess

        normalized = str(app_name).strip().lower()

        # 已有窗口优先
        try:
            for item in self.window_lookup():
                if normalized in item["title"].lower():
                    return (
                        f"{app_name} 已经打开。请复用现有窗口，"
                        "不要启动新实例。"
                    )
        except Exception:
            pass

        app = ALLOWED_APPS.get(normalized)
        if app is None:
            return (
                f"不允许新启动程序：{app_name}。"
                "当前白名单：记事本、计算器、资源管理器。"
                "如果程序已经打开，仍可操作现有窗口。"
            )

        if not self.voice.request_confirmation(
            f"程序：{app_name}\n允许启动吗？",
            operation_name="启动程序",
        ):
            return "用户拒绝了程序启动。"

        try:
            subprocess.Popen([app], shell=False)
            self.runtime.mark_activity("open_app")
            return f"已启动：{app_name}"
        except Exception as e:
            return f"启动失败：{e}"
