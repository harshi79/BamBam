"""
Tests for the standalone bot (repo-root ``main.py``).

The container entrypoint runs ``main.py`` whenever the YoriNetflix settings are
absent, so the two builds must behave the same way.  These tests import the
real module and exercise its own ``normalize_url`` / ``cookie_action_kb``.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT_MAIN = Path(__file__).resolve().parents[2] / "main.py"

pytestmark = pytest.mark.skipif(
    not ROOT_MAIN.is_file(), reason="standalone main.py not present"
)


@pytest.fixture(scope="module")
def standalone(tmp_path_factory):
    """Import repo-root ``main.py`` without touching the repo or the network."""
    workdir = tmp_path_factory.mktemp("standalone")
    import os

    saved = {
        key: os.environ.get(key)
        for key in ("BOT_TOKEN", "DB_NAME", "BACKUP_DIR", "LOG_DIR")
    }
    os.environ.update({
        # Bot() validates the token format but performs no network I/O here.
        "BOT_TOKEN": "123456:AAHstandalonetesttokenAAAAAAAAAAAAAAAAAAA",
        "DB_NAME": str(workdir / "test_bot.db"),
        "BACKUP_DIR": str(workdir / "backups"),
        "LOG_DIR": str(workdir / "logs"),
    })
    try:
        spec = importlib.util.spec_from_file_location("standalone_main", ROOT_MAIN)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_tv_default_is_the_official_activation_page(standalone):
    assert standalone.DEFAULT_TV_URL == "https://www.netflix.com/tv8"


def test_defaults_carry_no_credentials(standalone):
    for url in (
        standalone.DEFAULT_TV_URL,
        standalone.DEFAULT_PC_URL,
        standalone.DEFAULT_MOBILE_URL,
    ):
        assert "?" not in url
        assert "nftoken" not in url
        assert standalone.strip_credential_params(url) == url


def test_tv_button_falls_back_to_official_activation_page(standalone):
    tv = standalone.cookie_action_kb("", "", "").inline_keyboard[0][1]
    assert tv.text == "↗ Tᴠ"
    assert tv.url == standalone.DEFAULT_TV_URL


def test_auto_login_token_never_reaches_a_button(standalone):
    kb = standalone.cookie_action_kb(
        "https://www.netflix.com/account?nftoken=NFSECRET",
        "https://www.netflix.com/tv8?nftoken=NFSECRET",
        "https://www.netflix.com/login?nftoken=NFSECRET",
    )
    for button in kb.inline_keyboard[0]:
        assert "nftoken" not in button.url
        assert "NFSECRET" not in button.url


def test_plain_inventory_url_is_preserved(standalone):
    tv = standalone.cookie_action_kb(
        "https://www.netflix.com/account",
        "https://www.netflix.com/tv2",
        "https://www.netflix.com/login",
    ).inline_keyboard[0][1]
    assert tv.url == "https://www.netflix.com/tv2"
