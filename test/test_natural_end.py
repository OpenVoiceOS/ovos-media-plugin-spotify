"""Regression test: a track that ends naturally (``_wait_until_finished``
polls spotify and finds the target device inactive, no stop() ever
called) must report MediaState.END_OF_MEDIA / PlayerState.STOPPED on the
bus, exactly like an explicit stop does.

Also covers the bool contract on stop(): it must return True/False
instead of None.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_utils.fakebus import FakeBus
from ovos_utils.ocp import MediaState, PlayerState

from ovos_media_plugin_spotify import SpotifyOCPAudioService


def _service():
    bus = FakeBus()
    states = []
    player_states = []
    bus.on("ovos.common_play.media.state",
           lambda msg: states.append(msg.data.get("state")))
    bus.on("ovos.common_play.player.state",
           lambda msg: player_states.append(msg.data.get("state")))

    with patch("ovos_media_plugin_spotify.SpotifyClient"), \
         patch("ovos_media_plugin_spotify.SpotifydHooks"):
        svc = SpotifyOCPAudioService.__new__(SpotifyOCPAudioService)
        svc.spotify = MagicMock()
        svc.device_name = "OVOS"
        svc.hooks = MagicMock()
        svc.bus = bus
        svc._track_start_callback = None
        svc._now_playing = "spotify:track:x"
        svc._last_sync_ts = 12345.0
        svc._paused = False
    return svc, states, player_states


class TestNaturalEndOfMedia(unittest.TestCase):

    def test_natural_track_end_emits_end_of_media(self):
        svc, states, player_states = _service()

        # simulate _wait_until_finished's polling finding the device
        # inactive, with no stop() ever called by us
        svc.on_track_end()

        self.assertIn(MediaState.END_OF_MEDIA, states,
                       f"natural end-of-media never emitted END_OF_MEDIA; saw: {states}")
        self.assertIn(PlayerState.STOPPED, player_states,
                       f"natural end-of-media never emitted PlayerState.STOPPED; saw: {player_states}")

    def test_stop_returns_bool(self):
        svc, _, _ = _service()
        self.assertIs(svc.stop(), True)


if __name__ == "__main__":
    unittest.main()
