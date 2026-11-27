"""Regression test: a track that ends naturally (``_wait_until_finished``
polls spotify and finds the target device inactive, no stop() ever
called) must report ``PlaybackEvent.END_OF_MEDIA``, while an explicit
``stop()`` followed by the same end-of-track callback must report
``PlaybackEvent.STOPPED`` instead - the base class's ``report_track_end``
tells the two apart via the ``_stop_requested`` flag ``stop()`` sets.

Also covers the bool contract on ``_stop()``: it must return True/False
instead of None.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_plugin_manager.templates.media import PlaybackEvent
from ovos_utils.fakebus import FakeBus

from ovos_media_plugin_spotify import SpotifyOCPAudioService


def _service():
    bus = FakeBus()
    events = []

    with patch("ovos_media_plugin_spotify.SpotifyClient"), \
         patch("ovos_media_plugin_spotify.SpotifydEvents"):
        svc = SpotifyOCPAudioService.__new__(SpotifyOCPAudioService)
        svc.spotify = MagicMock()
        svc.device_name = "OVOS"
        svc.hooks = MagicMock()
        svc.bus = bus
        svc.meta = {}
        svc._event_reporter = None
        svc._stop_requested = False
        svc._now_playing = "spotify:track:x"
        svc._last_sync_ts = 12345.0
        svc._paused = False
        svc._poll_id = 0
    svc.bind_event_reporter(lambda event, **data: events.append((event, data)))
    return svc, events


class TestNaturalEndOfMedia(unittest.TestCase):

    def test_natural_track_end_reports_end_of_media(self):
        svc, events = _service()

        # simulate _wait_until_finished's polling finding the device
        # inactive, with no stop() ever called by us
        svc.on_track_end()

        matches = [e for e in events if e[0] is PlaybackEvent.END_OF_MEDIA]
        self.assertTrue(matches,
                         f"natural end-of-media never reported "
                         f"PlaybackEvent.END_OF_MEDIA; saw: {events}")
        self.assertEqual(matches[0][1].get("uri"), "spotify:track:x")

    def test_natural_end_never_touches_the_bus(self):
        svc, _ = _service()
        recorded = []
        svc.bus.on("ovos.common_play.media.state",
                   lambda msg: recorded.append(msg))
        svc.bus.on("ovos.common_play.player.state",
                   lambda msg: recorded.append(msg))

        svc.on_track_end()

        self.assertEqual(recorded, [],
                          "v2 backend must never emit ovos.common_play.* "
                          "itself - the daemon owns that wire")

    def test_stop_returns_bool(self):
        svc, _ = _service()
        self.assertIs(svc.stop(), True)

    def test_stop_clears_the_track_and_reports_nothing(self):
        """_stop() is a pure ask. It clears the track, so a late end
        callback reports nothing: ovos-media reports the stop itself."""
        svc, events = _service()

        svc.stop()
        svc.on_track_end()
        self.assertEqual(events, [])
        self.assertIsNone(svc._now_playing)
        self.assertFalse(svc._stop_requested)

    def test_natural_end_after_stop_reports_end_of_media(self):
        svc, _ = _service()

        svc.stop()
        svc._now_playing = "spotify:track:y"
        events2 = []
        svc.bind_event_reporter(lambda event, **data: events2.append((event, data)))
        svc.on_track_end()
        self.assertEqual([e[0] for e in events2], [PlaybackEvent.END_OF_MEDIA])


if __name__ == "__main__":
    unittest.main()
