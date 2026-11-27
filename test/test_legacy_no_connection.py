"""The legacy ovos-audio shim tolerates calls with no Spotify connection."""
import unittest
from unittest.mock import patch

from ovos_utils.fakebus import FakeBus

from ovos_media_plugin_spotify.audio import load_service


@patch("ovos_media_plugin_spotify.spotify_client.SpotifyClient.load_credentials")
class TestLegacyNoConnection(unittest.TestCase):
    def _service(self):
        config = {"backends": {"spotify": {"type": "ovos_spotify",
                                           "identifier": "OVOS"}}}
        return load_service(config, FakeBus())[0]

    def test_next_is_noop(self, _creds):
        self.assertIsNone(self._service().next())

    def test_previous_is_noop(self, _creds):
        self.assertIsNone(self._service().previous())

    def test_track_info_is_empty(self, _creds):
        self.assertEqual(self._service().track_info(), {})


if __name__ == "__main__":
    unittest.main()
