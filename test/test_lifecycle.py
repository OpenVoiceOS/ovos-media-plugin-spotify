"""Full play/pause/resume/stop lifecycle against a recording FakeBus and a
bound event reporter: the plugin must never emit ``ovos.common_play.*``
itself, and must report every physical transition as a ``PlaybackEvent``.

Per the v2 remote-backend contract, the verb methods (``play``/``pause``/
``resume``/``stop``) are pure asks with zero ``report()`` calls of their
own - the status listener (here, ``SpotifydHooks`` relaying spotifyd's own
notifications over the plugin-private bus) is the sole reporter, so these
tests drive the corresponding spotifyd bus event after each ask, exactly
as the real spotifyd daemon would once it confirms the transition.

The Spotify Connect API (spotipy) boundary is mocked; everything else -
the backend, ``SpotifydHooks`` bus wiring - is real.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message
from ovos_plugin_manager.templates.media import PlaybackEvent
from ovos_utils.fakebus import FakeBus

import ovos_media_plugin_spotify
from ovos_media_plugin_spotify import SpotifyOCPAudioService

DEVICE_NAME = "OVOS"
URI = "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
TRACK_ID = URI.split(":")[-1]


def _mock_client():
    client = MagicMock()
    client.devices = [{"name": DEVICE_NAME, "id": "dev-1", "is_active": True}]
    client.is_playing.return_value = True
    client.DEFAULT_VOLUME = 90
    return client


def _backend(bus):
    client = _mock_client()
    with patch.object(ovos_media_plugin_spotify, "SpotifyClient",
                       return_value=client):
        backend = SpotifyOCPAudioService({"identifier": DEVICE_NAME}, bus=bus)
    backend.spotify = client
    # avoid the blocking Connect-device poll
    backend._wait_until_finished = lambda: None
    return backend


class TestZeroBusStateEmission(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus_messages = []
        self.bus.on("ovos.common_play.media.state",
                    lambda msg: self.bus_messages.append(msg))
        self.bus.on("ovos.common_play.player.state",
                    lambda msg: self.bus_messages.append(msg))
        self.bus.on("ovos.common_play.track.state",
                    lambda msg: self.bus_messages.append(msg))
        self.events = []
        self.backend = _backend(self.bus)
        self.backend.bind_event_reporter(
            lambda event, **data: self.events.append((event, data)))

    def _kinds(self):
        return [e[0] for e in self.events]

    def _spotifyd(self, topic, **data):
        self.bus.emit(Message(topic, {"track_id": TRACK_ID, "duration": 1000,
                                       "position": 500, **data}))

    def test_full_lifecycle_reports_events_and_never_touches_the_bus(self):
        self.assertTrue(self.backend.load_track(URI))
        self.backend.play()
        self.assertIn(PlaybackEvent.TRACK_START, self._kinds())

        # pause() is a pure ask - only spotifyd's own notification reports
        self.backend.pause()
        self.assertNotIn(PlaybackEvent.PAUSED, self._kinds())
        self._spotifyd("spotifyd.pause")
        self.assertIn(PlaybackEvent.PAUSED, self._kinds())

        self.backend.resume()
        self.assertNotIn(PlaybackEvent.RESUMED, self._kinds())
        self._spotifyd("spotifyd.play")
        self.assertIn(PlaybackEvent.RESUMED, self._kinds())

        self.backend.stop()
        self.assertNotIn(PlaybackEvent.STOPPED, self._kinds())
        self._spotifyd("spotifyd.stop")
        self.assertIn(PlaybackEvent.STOPPED, self._kinds())

        self.assertEqual(self.bus_messages, [],
                          f"backend emitted ovos.common_play.* itself: "
                          f"{self.bus_messages}")

    def test_error_path_reports_error_with_uri_and_string(self):
        self.backend.load_track(URI)
        self.backend.spotify.play.side_effect = RuntimeError("boom")

        self.backend.play()

        errors = [d for k, d in self.events if k is PlaybackEvent.ERROR]
        self.assertTrue(errors, f"no ERROR reported; saw: {self.events}")
        self.assertEqual(errors[0]["uri"], URI)
        self.assertIsInstance(errors[0]["error"], str)

    def test_external_pause_via_spotifyd_hook_reports_paused(self):
        """Simulates the user pausing from the Spotify app directly - the
        backend only learns about it through spotifyd's own hook."""
        self.backend.load_track(URI)
        self.backend.play()
        self.events.clear()

        self._spotifyd("spotifyd.pause")

        self.assertIn(PlaybackEvent.PAUSED, self._kinds())
        self.assertTrue(self.backend._paused)

    def test_natural_end_via_spotifyd_reports_end_of_media_not_stopped(self):
        """No stop() call from us - spotifyd's end_of_track notification
        alone must resolve to END_OF_MEDIA."""
        self.backend.load_track(URI)
        self.backend.play()
        self.events.clear()

        self.bus.emit(Message("spotifyd.end_of_track", {}))

        kinds = self._kinds()
        self.assertIn(PlaybackEvent.END_OF_MEDIA, kinds)
        self.assertNotIn(PlaybackEvent.STOPPED, kinds)


if __name__ == "__main__":
    unittest.main()
