from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qingyuan.router import IntentRouter
from qingyuan.system_tools import SystemTools

# Planner only needs the Ollama import to exist; this smoke test never calls a model.
try:
    import ollama  # noqa: F401
except ModuleNotFoundError:
    import types
    fake_ollama = types.ModuleType("ollama")
    def _no_model_call(*args, **kwargs):
        raise RuntimeError("Smoke test must not call Ollama")
    fake_ollama.chat = _no_model_call
    sys.modules["ollama"] = fake_ollama

from qingyuan.planner import Planner
from qingyuan.config import MODEL


class FakeRuntime:
    def __init__(self):
        self.actions = []

    def record_desktop_action(self, action):
        self.actions.append(str(action))


class FakePermission:
    def __init__(self, request):
        self._request = str(request)
        self.ended = False

    def original_request(self):
        return self._request

    def require(self, capability, target=None):
        if capability in {"file_read", "file_write", "code_execute"}:
            return True, ""
        return False, f"unexpected capability in smoke test: {capability}"

    def end_task(self):
        self.ended = True
        return "TEST_PERMIT_ENDED"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_router():
    router = IntentRouter()
    require(
        router.route("清渊，给自己增加一个代码功能") == "coding",
        "self-development request did not route to coding",
    )
    require(
        router.route("清渊，检查你自己的代码，只检查不要修改") == "coding",
        "read-only self code inspection did not route to coding",
    )
    require(
        router.route("帮我写一段 Python 代码示例") == "chat",
        "plain code-generation request should remain chat",
    )



class FakeModelRouter:
    def for_planning(self):
        return MODEL


def test_planner():
    planner = Planner(FakeModelRouter())

    read_plan = planner.create(
        "coding",
        r"清渊，检查你自己的代码，只检查 C:\MyAgent\qingyuan\router.py，不要修改。",
    )
    require(read_plan.targets == [r"C:\MyAgent"], f"unexpected self-code target: {read_plan.targets}")
    require(read_plan.required_capabilities == ["file_read", "code_execute"], f"unexpected read-only caps: {read_plan.required_capabilities}")

    write_plan = planner.create(
        "coding",
        "清渊，给自己增加一个测试功能并运行编译检查",
    )
    require(write_plan.targets == [r"C:\MyAgent"], f"unexpected self-write target: {write_plan.targets}")
    require(
        write_plan.required_capabilities == ["file_read", "file_write", "code_execute"],
        f"unexpected write caps: {write_plan.required_capabilities}",
    )

def test_session_write_check_finish():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v580_") as td:
        root = Path(td).resolve()
        demo = root / "demo.py"
        demo.write_text("value = 1\n", encoding="utf-8")

        permission = FakePermission(f"请修改项目代码 {root}")
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)

        result = tools.code_begin_session(str(root))
        require("CODING_SESSION_STARTED" in result, result)

        result = tools.code_write_file("demo.py", "value = 2\n")
        require("CODE_WRITE_OK" in result, result)

        result = tools.code_finish_session()
        require("CODING_SESSION_NOT_VERIFIED" in result, result)

        result = tools.code_run_checks("compile", "demo.py")
        require("CHECK_OK" in result, result)

        result = tools.code_finish_session()
        require("CODING_SESSION_FINISHED" in result, result)
        require(permission.ended, "Task Permit was not revoked on finish")
        require(demo.read_text(encoding="utf-8") == "value = 2\n", "verified edit was not retained")


def test_exact_rollback():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v580_rb_") as td:
        root = Path(td).resolve()
        demo = root / "demo.py"
        original = b"answer = 41\n"
        demo.write_bytes(original)

        permission = FakePermission(f"修复项目代码 {root}")
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)

        require("CODING_SESSION_STARTED" in tools.code_begin_session(str(root)), "rollback session did not start")
        require("CODE_WRITE_OK" in tools.code_write_file("demo.py", "answer = 42\n"), "rollback edit failed")
        require(demo.read_bytes() != original, "rollback test edit did not change file")

        result = tools.code_rollback()
        require("CODE_ROLLBACK_OK" in result, result)
        require(demo.read_bytes() == original, "rollback did not restore original bytes exactly")



def test_compile_does_not_false_verify_non_python():
    with tempfile.TemporaryDirectory(prefix="qingyuan_v580_nonpy_") as td:
        root = Path(td).resolve()
        js = root / "demo.js"
        js.write_text("const x = 1;\n", encoding="utf-8")

        permission = FakePermission(f"修改项目代码 {root}")
        runtime = FakeRuntime()
        tools = SystemTools(runtime, permission)

        require("CODING_SESSION_STARTED" in tools.code_begin_session(str(root)), "non-python session did not start")
        require("CODE_WRITE_OK" in tools.code_write_file("demo.js", "const x = 2;\n"), "non-python edit failed")
        result = tools.code_run_checks("compile")
        require("CHECK_FAILED" in result, "Python compile must not verify non-Python edits")
        result = tools.code_finish_session()
        require("CODING_SESSION_NOT_VERIFIED" in result, "non-Python edit was falsely verified by Python compile")
        require("CODE_ROLLBACK_OK" in tools.code_rollback(), "non-Python rollback failed")

def main():
    print("Qingyuan Coding Agent v5.8.0 smoke test")
    print("=" * 54)
    test_router()
    print("[OK] Router: coding vs chat separation")
    test_planner()
    print("[OK] Planner: self-project scope + read/write capability split")
    test_session_write_check_finish()
    print("[OK] Session: write -> verification gate -> compile -> finish")
    test_exact_rollback()
    print("[OK] Rollback: exact session-local restore")
    test_compile_does_not_false_verify_non_python()
    print("[OK] Verification: Python compile cannot falsely verify non-Python edits")
    print("=" * 54)
    print("ALL_TESTS_OK")
    print("This smoke test only used temporary directories; C:\\MyAgent project/data were not modified.")


if __name__ == "__main__":
    main()
