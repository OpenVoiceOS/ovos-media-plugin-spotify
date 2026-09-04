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
         patch("ovos_media_plugin_spotify.SpotifydHooks"):
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

    def test_stop_then_end_callback_reports_stopped_not_end_of_media(self):
        """stop() itself (-> _stop()) is a pure ask and reports nothing;
        the STOPPED report only happens once the end-of-track callback
        fires, exactly like a natural end would - the only difference is
        which PlaybackEvent report_track_end resolves to, based on the
        _stop_requested flag stop() set."""
        svc, events = _service()

        svc.stop()
        self.assertEqual(events, [],
                          f"_stop() must be a pure ask and report nothing; saw: {events}")

        svc.on_track_end()

        kinds = [e[0] for e in events]
        self.assertIn(PlaybackEvent.STOPPED, kinds)
        self.assertNotIn(PlaybackEvent.END_OF_MEDIA, kinds)

    def test_stop_requested_flag_cleared_after_report(self):
        svc, _ = _service()

        svc.stop()
        svc.on_track_end()
        self.assertFalse(svc._stop_requested)

        # a subsequent natural end (no stop() in between) must report
        # END_OF_MEDIA again, not STOPPED
        svc._now_playing = "spotify:track:y"
        events2 = []
        svc.bind_event_reporter(lambda event, **data: events2.append((event, data)))
        svc.on_track_end()
        self.assertIn(PlaybackEvent.END_OF_MEDIA, [e[0] for e in events2])


if __name__ == "__main__":
    unittest.main()
