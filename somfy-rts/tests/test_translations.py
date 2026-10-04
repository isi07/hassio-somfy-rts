"""Every add-on option and port must have a translation in every language."""

import pathlib

import pytest
import yaml

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1]
LANGUAGES = ["de", "en"]


def _load(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def config() -> dict:
    return _load(ADDON_DIR / "config.yaml")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_all_options_translated(config: dict, lang: str) -> None:
    translation = _load(ADDON_DIR / "translations" / f"{lang}.yaml")
    assert set(translation["configuration"]) == set(config["schema"])
    for key, entry in translation["configuration"].items():
        assert entry.get("name"), f"{lang}: {key} has no name"
        assert entry.get("description"), f"{lang}: {key} has no description"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_all_ports_translated(config: dict, lang: str) -> None:
    translation = _load(ADDON_DIR / "translations" / f"{lang}.yaml")
    assert set(translation["network"]) == set(config["ports"])
