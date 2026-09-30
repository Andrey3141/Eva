"""
Тест ParameterRouterFacade: переключение между ml и кастыли
через Config.PARAMETER_ROUTER_MODE.
"""
import sys

import pytest

from assistant.intent.parameter.facade import ParameterRouterFacade
from кастыли import КастылиParameterRouter


class _FakeMLRouter:
    def extract_params(self, text, intent_name):
        return {"_from_ml": True}, [], [], {"mode": "ml"}


@pytest.fixture
def facade():
    return ParameterRouterFacade(
        ml_router=_FakeMLRouter(),
        kastyli_router=КастылиParameterRouter(),
    )


def test_mode_ml(facade, monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "PARAMETER_ROUTER_MODE", "ml")
    params, _a, _r, _d = facade.extract_params("привет", "answer")
    assert params.get("_from_ml") is True


def test_mode_kastyli(facade, monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "PARAMETER_ROUTER_MODE", "кастыли")
    params, _a, _r, _d = facade.extract_params(
        "поставь Иванову 2", "grade_student",
    )
    assert params.get("student") == "Иванову"
    assert params.get("grade") == 2


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_parameter_facade_mode.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
