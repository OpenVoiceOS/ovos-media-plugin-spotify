"""The legacy ovos-audio shim stops cleanly with no Spotify connection."""
import unittest
from unittest.mock import patch

from ovos_utils.fakebus import FakeBus

from ovos_media_plugin_spotify.audio import load_service


class TestLegacyStopNoConnection(unittest.TestCase):
    @patch("ovos_media_plugin_spotify.audio.LOG")
    @patch("ovos_media_plugin_spotify.spotify_client.SpotifyClient.load_credentials")
    def test_stop_without_connection_is_noop(self, _creds, log):
        config = {"backends": {"spotify": {"type": "ovos_spotify",
                                           "identifier": "OVOS"}}}
        service = load_service(config, FakeBus())[0]
        service.stop()
        service.stop()
        log.warning.assert_called_once_with("stop ignored: no Spotify connection")


if __name__ == "__main__":
    unittest.main()
