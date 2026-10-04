"""Tests for config.py and the option chain config.yaml → run.sh → config.py."""

import pathlib

import pytest
import yaml

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_tls_defaults(monkeypatch):
    from somfy_rts.config import load_config

    monkeypatch.delenv("SOMFY_MQTT_TLS", raising=False)
    monkeypatch.delenv("SOMFY_MQTT_TLS_VERIFY", raising=False)
    cfg = load_config()
    assert cfg.mqtt_tls is False
    assert cfg.mqtt_tls_verify is True


def test_tls_from_env(monkeypatch):
    from somfy_rts.config import load_config

    monkeypatch.setenv("SOMFY_MQTT_TLS", "true")
    monkeypatch.setenv("SOMFY_MQTT_TLS_VERIFY", "false")
    cfg = load_config()
    assert cfg.mqtt_tls is True
    assert cfg.mqtt_tls_verify is False


@pytest.mark.parametrize("key", sorted(
    yaml.safe_load((ADDON_DIR / "config.yaml").read_text(encoding="utf-8"))["schema"]
))
def test_every_option_reaches_config_py(key: str):
    """config.yaml option → read in run.sh → exported as SOMFY_* → read in config.py."""
    run_sh = (ADDON_DIR / "run.sh").read_text(encoding="utf-8")
    config_py = (ADDON_DIR / "somfy_rts" / "config.py").read_text(encoding="utf-8")
    env = f"SOMFY_{key.upper()}"
    assert f"_opt {key} " in run_sh, f"run.sh does not read {key}"
    assert f"export {env}=" in run_sh, f"run.sh does not export {env}"
    assert f'"{env}"' in config_py, f"config.py does not read {env}"
