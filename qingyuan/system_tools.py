import ctypes
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from datetime import datetime


class SystemTools:
    def __init__(self, runtime, permission):
        self.runtime = runtime
        self.permission = permission
        self._code_lock = threading.RLock()
        self._code_session = None
        self._last_code_session = None

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

    # ---------------- guarded coding agent ----------------

    _CODE_TEXT_EXTENSIONS = {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx",
        ".html", ".css", ".scss", ".json", ".toml",
        ".yaml", ".yml", ".ini", ".cfg", ".xml", ".sql",
        ".md", ".txt", ".bat", ".cmd", ".ps1", ".sh",
        ".gitignore", ".gitattributes",
    }

    _CODE_ALLOWED_BASENAMES = {
        "dockerfile",
        "makefile",
        "license",
        "readme",
        "pyproject.toml",
        "requirements.txt",
        ".gitignore",
        ".gitattributes",
    }

    _CODE_ALWAYS_PROTECTED_PARTS = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
    }

    _SELF_PROTECTED_TOP_LEVEL = {
        "data",
        "memory",
        "knowledge",
        "skills",
        "workspace",
        "logs",
        "voice",
        "models",
        "stt_env",
        "cosyvoice_env",
        ".venv",
        "cosyvoice",
    }

    _CODE_SENSITIVE_NAMES = {
        ".env",
        "credentials.json",
        "secrets.json",
        "secret.json",
        "token.json",
        "tokens.json",
        "ipc_token.txt",
    }

    @staticmethod
    def _code_norm(value) -> str:
        return os.path.normcase(
            os.path.abspath(str(value))
        )

    @staticmethod
    def _code_trim_output(text, limit=16000) -> str:
        value = str(text or "")
        if len(value) <= limit:
            return value
        return (
            value[:limit]
            + "\n\n[输出过长，仅保留前 "
            + str(limit)
            + " 个字符]"
        )

    def _code_session_data(self):
        with self._code_lock:
            session = self._code_session
            if not session or not session.get("active"):
                return None
            return session

    def _code_is_self_root(self, root: Path) -> bool:
        try:
            return (
                self._code_norm(root)
                == self._code_norm(r"C:\MyAgent")
            )
        except Exception:
            return False

    def _code_root_allowed_by_request(self, root: Path) -> bool:
        """
        二次约束：即使 Permit targets 为空，也不能让模型自行挑一个项目目录。

        - 清渊自我开发：原始命令明确提到“清渊/自己/你的代码/MyAgent”时，
          允许 C:\\MyAgent。
        - 其他项目：项目绝对路径必须出现在用户原始命令中。
        - workspace 项目：原始命令明确提到 workspace/工作区时允许。
        """
        try:
            request = str(
                self.permission.original_request()
            ).strip()
        except Exception:
            request = ""

        if not request:
            return False

        q = request.lower()
        root_text = str(root)
        root_lower = root_text.lower()

        if self._code_is_self_root(root):
            self_words = [
                "清渊",
                "自己",
                "你自己",
                "你的代码",
                "你的项目",
                "本地智能体",
                "myagent",
            ]
            return any(word in q for word in self_words)

        if root_lower in q:
            return True

        # 用户明确说“工作区/workspace”时，只允许 C:\MyAgent\workspace 内项目。
        try:
            workspace = Path(
                r"C:\MyAgent\workspace"
            ).resolve()
            root.relative_to(workspace)
            if (
                "workspace" in q
                or "工作区" in q
            ):
                return True
        except Exception:
            pass

        return False

    def _code_protection_reason(
        self,
        target: Path,
        *,
        for_write: bool,
    ):
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]

        try:
            relative = target.relative_to(root)
        except ValueError:
            return "拒绝执行：代码目标超出当前 Coding Session 项目根目录。"

        parts = [
            part.lower()
            for part in relative.parts
        ]

        if any(
            part in self._CODE_ALWAYS_PROTECTED_PARTS
            for part in parts
        ):
            return "拒绝执行：环境目录、缓存目录或 .git 不允许由 Coding Agent 修改/读取。"

        if (
            self._code_is_self_root(root)
            and parts
            and parts[0]
            in self._SELF_PROTECTED_TOP_LEVEL
        ):
            return (
                "拒绝执行：该路径属于清渊持久化数据/模型/环境保护区，"
                "Coding Agent 默认不可访问。"
            )

        name = target.name.lower()
        if (
            name in self._CODE_SENSITIVE_NAMES
            or name.startswith(".env")
        ):
            return "拒绝执行：敏感凭据/环境变量文件不允许由 Coding Agent 访问。"

        if for_write:
            suffix = target.suffix.lower()
            if (
                suffix not in self._CODE_TEXT_EXTENSIONS
                and name not in self._CODE_ALLOWED_BASENAMES
            ):
                return (
                    "拒绝写入：Coding Agent 只允许修改文本代码、配置和文档文件，"
                    f"当前文件类型：{suffix or '[无扩展名]'}。"
                )

        return ""

    def _code_target(
        self,
        value: str,
        *,
        must_exist: bool = False,
        for_write: bool = False,
    ):
        session = self._code_session_data()
        if session is None:
            return None, "当前没有有效 Coding Session。请先调用 code_begin_session。"

        root = session["root"]
        raw = Path(str(value)).expanduser()

        if raw.is_absolute():
            target = raw.resolve()
        else:
            target = (root / raw).resolve()

        reason = self._code_protection_reason(
            target,
            for_write=for_write,
        )
        if reason:
            return None, reason

        if must_exist and not target.exists():
            return None, f"代码路径不存在：{target}"

        return target, ""

    def _code_run_process(
        self,
        args,
        *,
        cwd: Path,
        timeout: int,
    ):
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        return subprocess.run(
            [str(x) for x in args],
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout)),
            creationflags=creationflags,
        )

    def _code_python(self, root: Path) -> str:
        candidates = [
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "Scripts" / "python.exe",
        ]

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

        return sys.executable

    def code_begin_session(
        self,
        project_root: str,
    ) -> str:
        """
        开始一次受保护的代码修改会话。

        不修改任何文件，只建立本次项目根目录、Git 基线和内存回滚点容器。
        必须先获得 file_read；只读会话不要求 code_execute。
        只有需要 Git/compile/pytest/unittest 时才要求 code_execute；真正写代码仍需 file_write。
        """
        root = self._path(project_root)

        ok, reason = self.permission.require(
            "file_read",
            str(root),
        )
        if not ok:
            return reason

        if not root.exists() or not root.is_dir():
            return f"无法开始 Coding Session：项目目录不存在：{root}"

        if not self._code_root_allowed_by_request(root):
            return (
                "拒绝执行：用户原始命令没有明确允许把该目录作为代码项目根目录。"
            )

        with self._code_lock:
            if (
                self._code_session
                and self._code_session.get("active")
            ):
                return (
                    "当前已有 Coding Session："
                    + str(self._code_session["root"])
                    + "。请先完成或回滚当前会话。"
                )

            can_execute = bool(
                getattr(self.permission, "has", lambda *_: False)("code_execute")
            )
            git_exe = shutil.which("git") if can_execute else None
            git_head = ""
            git_status = ""
            git_baseline_skipped = not can_execute

            if git_exe and (root / ".git").exists():
                try:
                    head = self._code_run_process(
                        [git_exe, "rev-parse", "HEAD"],
                        cwd=root,
                        timeout=20,
                    )
                    if head.returncode == 0:
                        git_head = head.stdout.strip()

                    status = self._code_run_process(
                        [
                            git_exe,
                            "status",
                            "--short",
                            "--untracked-files=all",
                        ],
                        cwd=root,
                        timeout=20,
                    )
                    git_status = self._code_trim_output(
                        (status.stdout or "")
                        + (status.stderr or ""),
                        6000,
                    ).strip()
                except Exception as e:
                    git_status = f"Git 基线读取失败：{e}"

            self._code_session = {
                "active": True,
                "root": root,
                "started_at": datetime.now(),
                "git_exe": git_exe,
                "git_head": git_head,
                "initial_git_status": git_status,
                "backups": {},
                "modified": [],
                "created": [],
                "revision": 0,
                "checks": [],
            }

        self.runtime.record_desktop_action(
            "coding:begin"
        )

        if git_baseline_skipped:
            baseline = "只读会话未申请 code_execute，已跳过 Git 基线"
        else:
            baseline = (
                "clean"
                if not git_status
                else "存在预先已有的未提交改动（Coding Agent 不会自动覆盖/提交这些改动）"
            )

        return (
            "CODING_SESSION_STARTED\n"
            f"项目根目录：{root}\n"
            f"Git HEAD：{git_head or '不可用/非 Git 项目'}\n"
            f"启动基线：{baseline}\n"
            "保护策略：仅允许项目内文本代码；C:\\MyAgent 的 data/memory/knowledge/skills/"
            "workspace/logs/voice/models/环境目录默认禁止访问；不提供任意 shell。"
        )

    def code_session_status(self) -> str:
        """查看当前 Coding Session 的只读状态。"""
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        modified = [
            str(path.relative_to(session["root"]))
            for path in session["modified"]
        ]
        checks = session["checks"][-5:]

        return (
            "CODING_SESSION_STATUS\n"
            f"root={session['root']}\n"
            f"revision={session['revision']}\n"
            f"modified={modified}\n"
            f"checks={checks}"
        )

    def code_project_tree(
        self,
        project_root: str = "",
        max_depth: int = 3,
    ) -> str:
        """列出当前 Coding Session 项目树，自动跳过环境、缓存和保护区。"""
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]
        if project_root:
            requested = self._path(project_root)
            if requested != root:
                return "拒绝执行：project_root 必须等于当前 Coding Session 根目录。"

        ok, reason = self.permission.require(
            "file_read",
            str(root),
        )
        if not ok:
            return reason

        try:
            depth_limit = max(1, min(5, int(max_depth)))
        except Exception:
            depth_limit = 3

        lines = []
        count = 0
        max_items = 500

        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            try:
                rel_dir = current_path.relative_to(root)
            except ValueError:
                continue

            depth = len(rel_dir.parts)
            if depth >= depth_limit:
                dirs[:] = []

            kept_dirs = []
            for name in sorted(dirs):
                candidate = current_path / name
                reason = self._code_protection_reason(
                    candidate,
                    for_write=False,
                )
                if reason:
                    continue
                kept_dirs.append(name)
            dirs[:] = kept_dirs

            if rel_dir.parts:
                lines.append(
                    "  " * max(0, depth - 1)
                    + f"[{rel_dir.name}/]"
                )
                count += 1

            for name in sorted(files):
                candidate = current_path / name
                reason = self._code_protection_reason(
                    candidate,
                    for_write=False,
                )
                if reason:
                    continue

                lines.append(
                    "  " * depth
                    + name
                )
                count += 1
                if count >= max_items:
                    lines.append(
                        "[项目树过长，仅显示前 500 项]"
                    )
                    break

            if count >= max_items:
                break

        self.runtime.record_desktop_action(
            "coding:tree"
        )

        return "\n".join(lines) if lines else "项目目录为空或全部属于保护区。"

    def code_read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = 400,
    ) -> str:
        """按行读取当前 Coding Session 内的文本代码文件。"""
        target, reason = self._code_target(
            path,
            must_exist=True,
            for_write=False,
        )
        if reason:
            return reason

        ok, reason = self.permission.require(
            "file_read",
            str(target),
        )
        if not ok:
            return reason

        if not target.is_file():
            return f"不是代码文件：{target}"

        try:
            first = max(1, int(start_line))
            last = max(first, int(end_line))
            last = min(last, first + 599)

            text = target.read_text(
                encoding="utf-8",
            )
            rows = text.splitlines()
            selected = rows[first - 1:last]

            numbered = [
                f"{index:>5}: {line}"
                for index, line in enumerate(
                    selected,
                    start=first,
                )
            ]

            self.runtime.record_desktop_action(
                "coding:read"
            )

            result = "\n".join(numbered)
            return self._code_trim_output(
                result,
                30000,
            )

        except UnicodeDecodeError:
            return "拒绝读取：Coding Agent 只读取 UTF-8 文本代码。"
        except Exception as e:
            return f"代码读取失败：{e}"

    def code_write_file(
        self,
        path: str,
        content: str,
    ) -> str:
        """
        原子写入当前 Coding Session 内的文本代码文件。

        第一次修改某文件前会把原内容保存在进程内存中，用于本会话 rollback。
        不会自动提交 Git，也不会写入清渊持久化 memory/data/knowledge/skills。
        """
        target, reason = self._code_target(
            path,
            must_exist=False,
            for_write=True,
        )
        if reason:
            return reason

        ok, reason = self.permission.require(
            "file_write",
            str(target),
        )
        if not ok:
            return reason

        value = str(content)
        if len(value) > 600000:
            return "拒绝写入：单个 Coding Agent 文本文件最多 600000 字符。"

        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        try:
            with self._code_lock:
                key = str(target)
                if key not in session["backups"]:
                    if target.exists():
                        if not target.is_file():
                            return f"拒绝写入：目标不是普通文件：{target}"
                        if target.stat().st_size > 2_000_000:
                            return "拒绝写入：原文件超过 2MB，不适合自动整文件改写。"
                        session["backups"][key] = target.read_bytes()
                    else:
                        session["backups"][key] = None
                        session["created"].append(target)

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                temp_path = target.with_name(
                    target.name + ".qingyuan_tmp"
                )

                try:
                    temp_path.write_text(
                        value,
                        encoding="utf-8",
                    )
                    os.replace(
                        str(temp_path),
                        str(target),
                    )
                finally:
                    try:
                        if temp_path.exists():
                            temp_path.unlink()
                    except Exception:
                        pass

                if target not in session["modified"]:
                    session["modified"].append(target)

                session["revision"] += 1

            self.runtime.record_desktop_action(
                "coding:write"
            )

            return (
                "CODE_WRITE_OK: "
                + str(target.relative_to(session["root"]))
                + f"；revision={session['revision']}"
            )

        except UnicodeDecodeError:
            return "代码写入失败：原文件不是 UTF-8 文本。"
        except Exception as e:
            return f"代码写入失败：{type(e).__name__}: {e}"

    def code_git_status(self) -> str:
        """读取当前 Coding Session 项目的 Git 状态，不执行 add/commit/reset。"""
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]

        ok, reason = self.permission.require(
            "code_execute",
            str(root),
        )
        if not ok:
            return reason

        git_exe = session.get("git_exe")
        if not git_exe or not (root / ".git").exists():
            return "CODE_GIT_STATUS: 当前项目不是可用的 Git 仓库。"

        try:
            result = self._code_run_process(
                [
                    git_exe,
                    "status",
                    "--short",
                    "--untracked-files=all",
                ],
                cwd=root,
                timeout=30,
            )
            output = self._code_trim_output(
                (result.stdout or "")
                + (result.stderr or ""),
                12000,
            ).strip()

            return (
                "CODE_GIT_STATUS\n"
                + (output or "working tree clean")
            )
        except Exception as e:
            return f"Git 状态读取失败：{e}"

    def code_git_diff(self) -> str:
        """只查看本次 Coding Session 已触碰文件的 Git diff。"""
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]
        ok, reason = self.permission.require(
            "code_execute",
            str(root),
        )
        if not ok:
            return reason

        modified = list(session["modified"])
        if not modified:
            return "CODE_GIT_DIFF: 本会话尚未修改任何文件。"

        git_exe = session.get("git_exe")
        if not git_exe or not (root / ".git").exists():
            names = [
                str(path.relative_to(root))
                for path in modified
            ]
            return (
                "CODE_GIT_DIFF: 非 Git 项目；本会话修改文件：\n- "
                + "\n- ".join(names)
            )

        try:
            rels = [
                str(path.relative_to(root))
                for path in modified
                if path.exists()
            ]

            args = [
                git_exe,
                "diff",
                "--no-ext-diff",
                "--",
                *rels,
            ]

            result = self._code_run_process(
                args,
                cwd=root,
                timeout=60,
            )

            output = self._code_trim_output(
                (result.stdout or "")
                + (result.stderr or ""),
                24000,
            ).strip()

            created = [
                str(path.relative_to(root))
                for path in session["created"]
                if path.exists()
            ]

            extra = ""
            if created:
                extra = (
                    "\n\n[本会话新建文件]\n- "
                    + "\n- ".join(created)
                )

            return (
                "CODE_GIT_DIFF\n"
                + (output or "tracked files currently have no textual diff")
                + extra
            )
        except Exception as e:
            return f"Git diff 读取失败：{e}"

    def code_run_checks(
        self,
        check: str = "compile",
        target: str = "",
    ) -> str:
        """
        运行严格白名单代码检查。

        check 只允许：compile / pytest / unittest。
        不接受 shell 字符串，也不接受任意命令参数。
        """
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]
        ok, reason = self.permission.require(
            "code_execute",
            str(root),
        )
        if not ok:
            return reason

        mode = str(check).strip().lower()
        aliases = {
            "compile": "compile",
            "py_compile": "compile",
            "编译": "compile",
            "pytest": "pytest",
            "test": "pytest",
            "测试": "pytest",
            "unittest": "unittest",
            "unit": "unittest",
        }
        mode = aliases.get(mode, "")

        if not mode:
            return "拒绝执行：code_run_checks 只允许 compile / pytest / unittest。"

        python_exe = self._code_python(root)
        args = []
        timeout = 180

        target_path = None
        if str(target).strip():
            target_path, reason = self._code_target(
                str(target).strip(),
                must_exist=True,
                for_write=False,
            )
            if reason:
                return reason

        if mode == "compile":
            modified_existing = [
                path
                for path in session["modified"]
                if path.exists() and path.is_file()
            ]
            modified_non_python = [
                path
                for path in modified_existing
                if path.suffix.lower() not in {".py", ".pyi"}
            ]

            # compile 是 Python 语法检查。若本 revision 同时改了 JS/TS/配置等，
            # 不能靠“顺便 compile 了别的 Python 文件”给整个 revision 盖章。
            if modified_non_python:
                names = [
                    str(path.relative_to(root))
                    for path in modified_non_python[:12]
                ]
                with self._code_lock:
                    session["checks"].append({
                        "check": mode,
                        "ok": False,
                        "revision": session["revision"],
                        "returncode": "unsupported_modified_type",
                    })
                return (
                    f"CHECK_FAILED: compile; revision={session['revision']}; "
                    "当前 revision 包含非 Python 修改，不能用 Python compile "
                    "作为完整验证。可在项目适用时改用 pytest/unittest。\n"
                    f"未被 compile 覆盖：{names}"
                )

            if target_path is not None:
                if target_path.is_file():
                    if target_path.suffix.lower() not in {".py", ".pyi"}:
                        return (
                            f"CHECK_FAILED: compile; revision={session['revision']}; "
                            "compile 只接受 Python 文件或目录。"
                        )
                    args = [
                        python_exe,
                        "-m",
                        "py_compile",
                        str(target_path),
                    ]
                else:
                    args = [
                        python_exe,
                        "-m",
                        "compileall",
                        "-q",
                        str(target_path),
                    ]
            else:
                py_files = [
                    path
                    for path in modified_existing
                    if path.suffix.lower() in {".py", ".pyi"}
                ]

                if py_files:
                    args = [
                        python_exe,
                        "-m",
                        "py_compile",
                        *[str(path) for path in py_files],
                    ]
                elif (root / "qingyuan").is_dir():
                    # 只读 Coding Session 没有修改文件时，可以检查现有 Python 包。
                    args = [
                        python_exe,
                        "-m",
                        "compileall",
                        "-q",
                        str(root / "qingyuan"),
                    ]
                else:
                    args = [
                        python_exe,
                        "-m",
                        "compileall",
                        "-q",
                        str(root),
                    ]

        elif mode == "pytest":
            args = [
                python_exe,
                "-m",
                "pytest",
                "-q",
            ]
            if target_path is not None:
                args.append(str(target_path))
            timeout = 300

        else:
            args = [
                python_exe,
                "-m",
                "unittest",
                "discover",
                "-v",
            ]
            if target_path is not None:
                search_dir = (
                    target_path
                    if target_path.is_dir()
                    else target_path.parent
                )
                args.extend([
                    "-s",
                    str(search_dir),
                ])
            timeout = 300

        try:
            result = self._code_run_process(
                args,
                cwd=root,
                timeout=timeout,
            )

            output = self._code_trim_output(
                (result.stdout or "")
                + (result.stderr or ""),
                16000,
            ).strip()

            ok_result = result.returncode == 0

            with self._code_lock:
                session["checks"].append({
                    "check": mode,
                    "ok": ok_result,
                    "revision": session["revision"],
                    "returncode": result.returncode,
                })

            self.runtime.record_desktop_action(
                "coding:check"
            )

            marker = (
                "CHECK_OK"
                if ok_result
                else "CHECK_FAILED"
            )

            return (
                f"{marker}: {mode}; "
                f"revision={session['revision']}; "
                f"returncode={result.returncode}\n"
                + (output or "[no output]")
            )

        except subprocess.TimeoutExpired:
            with self._code_lock:
                session["checks"].append({
                    "check": mode,
                    "ok": False,
                    "revision": session["revision"],
                    "returncode": "timeout",
                })
            return (
                f"CHECK_FAILED: {mode}; revision={session['revision']}; "
                "检查超时，进程已终止。"
            )
        except Exception as e:
            return (
                f"CHECK_FAILED: {mode}; revision={session['revision']}; "
                f"{type(e).__name__}: {e}"
            )

    def code_rollback(self) -> str:
        """只回滚本 Coding Session 自己修改过的文件，不碰其他预先存在改动。"""
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        root = session["root"]
        ok, reason = self.permission.require(
            "file_write",
            str(root),
        )
        if not ok:
            return reason

        restored = []
        errors = []

        with self._code_lock:
            for raw_path, backup in list(
                session["backups"].items()
            ):
                target = Path(raw_path)
                try:
                    if backup is None:
                        if target.exists() and target.is_file():
                            target.unlink()
                    else:
                        target.parent.mkdir(
                            parents=True,
                            exist_ok=True,
                        )
                        target.write_bytes(backup)

                    restored.append(
                        str(target.relative_to(root))
                    )
                except Exception as e:
                    errors.append(
                        f"{target}: {e}"
                    )

            if not errors:
                session["backups"] = {}
                session["modified"] = []
                session["created"] = []
                session["revision"] += 1
                session["checks"] = []

        self.runtime.record_desktop_action(
            "coding:rollback"
        )

        if errors:
            return (
                "代码回滚失败：\n- "
                + "\n- ".join(errors)
            )

        return (
            "CODE_ROLLBACK_OK: 仅恢复了本会话触碰的文件。\n"
            + (
                "恢复文件：\n- "
                + "\n- ".join(restored)
                if restored
                else "本会话没有需要恢复的文件。"
            )
        )

    def code_finish_session(self) -> str:
        """
        完成 Coding Session。

        如果本会话写过代码，必须至少有一次针对当前最新 revision 的成功检查，
        否则拒绝宣布完成。
        """
        session = self._code_session_data()
        if session is None:
            return "当前没有有效 Coding Session。"

        current_revision = session["revision"]
        modified = list(session["modified"])

        verified = any(
            bool(item.get("ok"))
            and item.get("revision") == current_revision
            for item in session["checks"]
        )

        if modified and not verified:
            return (
                "CODING_SESSION_NOT_VERIFIED: 当前最新代码 revision "
                f"{current_revision} 尚未通过 compile/pytest/unittest 检查；"
                "不得宣布代码任务完成。"
            )

        root = session["root"]
        names = [
            str(path.relative_to(root))
            for path in modified
        ]

        with self._code_lock:
            session["active"] = False
            self._last_code_session = session

        self.runtime.record_desktop_action(
            "coding:finish"
        )

        try:
            permit_result = self.permission.end_task()
        except Exception as e:
            permit_result = f"Task Permit 收回异常：{e}"

        return (
            "CODING_SESSION_FINISHED\n"
            f"项目：{root}\n"
            f"最终 revision：{current_revision}\n"
            f"修改文件：{names or []}\n"
            "代码修改已保留在工作树中；未自动 git add、commit、push。\n"
            f"权限状态：{permit_result}"
        )

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
