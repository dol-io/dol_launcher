from __future__ import annotations

import webbrowser


def open_browser(url: str, enabled: bool = True) -> bool:
    if not enabled:
        return False
    return webbrowser.open(url)
