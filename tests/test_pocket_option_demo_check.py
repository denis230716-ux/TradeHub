from tools.pocket_option_demo_check import get_demo_ssid


def test_demo_ssid_validation(monkeypatch):
    monkeypatch.setenv(
        "POCKET_OPTION_SSID",
        '42["auth",{"session":"example","isDemo":1,"uid":123,"platform":8}]',
    )
    assert get_demo_ssid().startswith('42["auth",')
