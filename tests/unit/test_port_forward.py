"""Port-forward manager tests."""

from unittest.mock import patch

from token_factory.runtime.port_forward import (
    _load_state,
    _save_state,
    list_forwards,
    stop_all,
)


def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("token_factory.runtime.port_forward.runtime_dir", lambda: tmp_path)
    _save_state({"forwards": [{"name": "test", "local_port": 9999, "pid": 1}]})
    state = _load_state()
    assert len(state["forwards"]) == 1


def test_stop_all_clears_state(tmp_path, monkeypatch):
    monkeypatch.setattr("token_factory.runtime.port_forward.runtime_dir", lambda: tmp_path)
    _save_state({"forwards": [{"name": "test", "local_port": 8080, "pid": 999999}]})
    with patch("token_factory.runtime.port_forward._pid_alive", return_value=False):
        stop_all()
    assert _load_state()["forwards"] == []


def test_list_forwards_prunes_dead(tmp_path, monkeypatch):
    monkeypatch.setattr("token_factory.runtime.port_forward.runtime_dir", lambda: tmp_path)
    _save_state({"forwards": [{"name": "dead", "local_port": 8080, "pid": 999999}]})
    with patch("token_factory.runtime.port_forward._pid_alive", return_value=False):
        forwards = list_forwards()
    assert forwards[0]["alive"] is False
    assert _load_state()["forwards"] == []
