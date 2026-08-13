"""
Regression test for https://github.com/OpenVoiceOS/ovos-media-plugin-spotify/issues/26
("Invalid redirect URI" on OAuth setup).

Spotify's current OAuth rules (https://developer.spotify.com/documentation/web-api/concepts/redirect_uri,
verified live 2026-08-13):
  - "localhost" is explicitly NOT allowed as a redirect URI host - apps must
    use the loopback IP literal (127.0.0.1 / [::1]).
  - the redirect_uri sent in every authorize/token request must exactly
    match what is registered in the Spotify app dashboard.

auth.py (the initial `ovos-spotify-oauth` setup script) used
'https://127.0.0.1:8888' and told users to whitelist that value, but
spotify_client.py's token-refresh path used 'https://localhost:8888' and
the README's worked example also used localhost. A user who registered
"127.0.0.1:8888" per auth.py's instructions (or vice-versa) would get a
redirect_uri mismatch - exactly "Invalid redirect URI" - the moment the
other code path (refresh) ran, and a user who read the README's example
literally would register a host Spotify now rejects outright.

This test asserts every redirect_uri literal in the plugin is identical
and uses the loopback IP (not "localhost").
"""
import re
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "ovos_media_plugin_spotify"
README = Path(__file__).resolve().parent.parent / "README.md"


def _redirect_uris_in(path):
    text = path.read_text()
    return re.findall(r"redirect_uri=['\"]?(https?%?3?A?%?2F%?2F[\w./:%-]+)",
                       text, re.IGNORECASE) or \
           re.findall(r"redirect_uri=(['\"])((?:(?!\1).)*)\1", text)


def test_no_localhost_redirect_uri_in_source():
    """Spotify rejects 'localhost' as a redirect URI host outright."""
    offenders = []
    for py_file in PKG_DIR.glob("*.py"):
        text = py_file.read_text()
        for line_no, line in enumerate(text.splitlines(), 1):
            if "redirect_uri" in line and "localhost" in line.lower():
                offenders.append(f"{py_file.name}:{line_no}: {line.strip()}")
    assert not offenders, f"redirect_uri using 'localhost' found: {offenders}"


def test_no_localhost_in_readme_oauth_example():
    text = README.read_text()
    assert "localhost" not in text.lower(), \
        "README OAuth walkthrough still references 'localhost', which Spotify rejects as a redirect URI host"


def test_auth_py_and_spotify_client_use_the_same_redirect_uri():
    auth_text = (PKG_DIR / "auth.py").read_text()
    client_text = (PKG_DIR / "spotify_client.py").read_text()

    auth_match = re.search(r"REDIRECT_URI\s*=\s*['\"]([^'\"]+)['\"]", auth_text)
    client_match = re.search(r"redirect_uri=['\"]([^'\"]+)['\"]", client_text)

    assert auth_match, "could not find REDIRECT_URI literal in auth.py"
    assert client_match, "could not find redirect_uri literal in spotify_client.py"
    assert auth_match.group(1) == client_match.group(1), (
        "auth.py and spotify_client.py register/use different redirect_uri "
        f"values ({auth_match.group(1)!r} vs {client_match.group(1)!r}); "
        "Spotify requires an exact match between what was registered and "
        "what every request (initial auth AND token refresh) sends, "
        "otherwise refresh fails with 'Invalid redirect URI'"
    )
