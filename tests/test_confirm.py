import pytest

from prusaslicer_mcp.confirm import ConfirmationGate
from prusaslicer_mcp.errors import ConfirmationError


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


PARAMS = {"host": "Kobra", "job_id": "12"}


def test_happy_path():
    g = ConfirmationGate()
    code = g.request("cancel_print", PARAMS)
    assert len(code) == 8
    g.consume(code, "cancel_print", dict(PARAMS))


def test_second_use_fails():
    g = ConfirmationGate()
    code = g.request("cancel_print", PARAMS)
    g.consume(code, "cancel_print", PARAMS)
    with pytest.raises(ConfirmationError):
        g.consume(code, "cancel_print", PARAMS)


def test_expired():
    clock = Clock()
    g = ConfirmationGate(clock=clock)
    code = g.request("cancel_print", PARAMS)
    clock.t += 121
    with pytest.raises(ConfirmationError) as e:
        g.consume(code, "cancel_print", PARAMS)
    assert "caduc" in e.value.message


def test_changed_params_fail():
    g = ConfirmationGate()
    code = g.request("start_print", {"host": "Kobra", "remote": "a.gcode"})
    with pytest.raises(ConfirmationError):
        g.consume(code, "start_print", {"host": "Kobra", "remote": "b.gcode"})


def test_other_action_fails():
    g = ConfirmationGate()
    code = g.request("pause_print", PARAMS)
    with pytest.raises(ConfirmationError):
        g.consume(code, "cancel_print", PARAMS)


def test_other_job_fails():
    g = ConfirmationGate()
    code = g.request("cancel_print", PARAMS)
    with pytest.raises(ConfirmationError):
        g.consume(code, "cancel_print", {"host": "Kobra", "job_id": "13"})


def test_unknown_code():
    with pytest.raises(ConfirmationError):
        ConfirmationGate().consume("nope", "cancel_print", PARAMS)
