import os

def get_demo_ssid() -> str:
    value = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not value:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    if not value.startswith('42["auth",'):
        raise ValueError("POCKET_OPTION_SSID must be a complete auth frame")
    if '"isDemo":1' not in value:
        raise ValueError("POCKET_OPTION_SSID must be a Demo auth frame")
    return value
