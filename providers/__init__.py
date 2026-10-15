"""프로바이더 자동 등록.

providers/ 와 plugins/ 폴더의 .py 파일에서 Provider를 상속하고 `type`이 있는 클래스를 찾아 등록한다.
새 AI를 추가할 때 이 파일을 고칠 필요는 없다. 이름이 _로 시작하는 파일은 건너뛴다.
"""
import importlib
import importlib.util
import inspect
import os
import pkgutil
import traceback

from .base import Provider, ProviderError, Row

PLUGINS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
REGISTRY = {}
LOAD_ERRORS = []  # (파일 이름, 오류 문자열) — 위젯이 widget.log에 남긴다


def _register(module):
    for obj in vars(module).values():
        if inspect.isclass(obj) and issubclass(obj, Provider) and obj is not Provider and obj.type:
            REGISTRY.setdefault(obj.type, obj)


def discover():
    """다시 호출하면 plugins/를 새로 읽는다 (위젯의 "설정 다시 불러오기")."""
    REGISTRY.clear()
    LOAD_ERRORS.clear()
    for info in pkgutil.iter_modules(__path__):
        if not info.name.startswith("_"):
            _register(importlib.import_module(f"{__name__}.{info.name}"))
    if not os.path.isdir(PLUGINS_DIR):
        return
    for fname in sorted(os.listdir(PLUGINS_DIR)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"usage_plugins.{fname[:-3]}",
                                                          os.path.join(PLUGINS_DIR, fname))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _register(module)
        except Exception:  # noqa: BLE001 — 플러그인 하나가 깨져도 위젯은 떠야 함
            LOAD_ERRORS.append((fname, traceback.format_exc()))


discover()
