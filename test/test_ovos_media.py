"""Drive the v2 backend through the ovos-media AudioService.

The Spotify client is a mock: ``devices`` controls whether the Connect
device is active, so the inactivity poll sees a natural end.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message
from ovos_media.media_backends.audio import AudioService
from ovos_plugin_manager.templates.media import PlaybackEvent
from ovos_utils.fakebus import FakeBus
from ovos_utils.ocp import MediaState

import ovos_media_plugin_spotify
from ovos_media_plugin_spotify import SpotifyOCPAudioService

DEVICE = "ovos-test"
A = "spotify:track:aaa"
B = "spotify:track:bbb"


def _wait(cond, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class TestThroughAudioService(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.client = MagicMock()
        self.client.devices = [{"name": DEVICE, "id": "dev-1", "is_active": True}]
        self.client.is_playing.return_value = True
        with patch.object(ovos_media_plugin_spotify, "SpotifyClient",
                          return_value=self.client):
            self.backend = SpotifyOCPAudioService({"identifier": DEVICE},
                                                  bus=self.bus)
        self.backend.poll_interval = 0.02
        self.external = []
        self.svc = AudioService(self.bus, config={}, autoload=False,
                                on_external_event=self.external.append)
        self.svc.services = [self.backend]
        self.media_states = []
        self.track_states = []
        self.bus.on("ovos.common_play.media.state",
                    lambda m: self.media_states.append(m.data["state"]))
        self.bus.on("ovos.common_play.track.state",
                    lambda m: self.track_states.append(m.data["state"]))

    def tearDown(self):
        self.backend._now_playing = None  # ends any poll thread

    def _set_active(self, active):
        self.client.devices = [{"name": DEVICE, "id": "dev-1",
                                "is_active": active}]

    def _ends(self):
        return self.media_states.count(MediaState.END_OF_MEDIA)

    def test_play_returns_while_track_plays(self):
        worker = threading.Thread(target=self.svc.play, args=(A,), daemon=True)
        worker.start()
        worker.join(1.0)
        self.assertFalse(worker.is_alive())

    def test_natural_end(self):
        self.svc.play(A)
        self.assertEqual(len(self.track_states), 1)
        self.client.play.assert_called_once_with([A], dev_id="dev-1")
        self._set_active(False)
        self.assertTrue(_wait(lambda: self._ends() == 1))
        time.sleep(0.1)
        self.assertEqual(self._ends(), 1)
        self.assertIsNone(self.backend.get_track_position())

    def test_switch_reports_one_end(self):
        self.svc.play(A)
        self.svc.play(B)
        self.assertEqual(self.backend._now_playing, B)
        self._set_active(False)
        self.assertTrue(_wait(lambda: self._ends() == 1))
        time.sleep(0.1)
        self.assertEqual(self._ends(), 1)
        self.assertEqual(len(self.track_states), 2)

    def test_stale_end_of_replaced_track_keeps_new_track(self):
        events = []
        self.svc.play(A)
        self.svc.play(B)
        reporter = self.backend._event_reporter
        self.backend.bind_event_reporter(
            lambda e, **d: (events.append((e, d)), reporter(e, **d)))
        self.backend.on_track_end(A)
        self.assertEqual(events, [(PlaybackEvent.END_OF_MEDIA, {"uri": A})])
        self.assertEqual(self._ends(), 0)  # ovos-media drops it by uri
        self.assertEqual(self.backend._now_playing, B)

    def test_stop(self):
        self.svc.play(A)
        self.svc.play_start_time -= 2  # past the 1 s start guard
        self.svc.stop()
        self.client.pause.assert_called_once_with("dev-1")
        self.assertEqual(self._ends(), 1)
        self.assertIsNone(self.svc.get_track_position())

    def test_pause_and_resume_reach_external_event(self):
        self.svc.play(A)
        self.svc.pause()
        self.client.pause.assert_called_once_with("dev-1")
        self.bus.emit(Message("spotifyd.pause", {"track_id": "aaa",
                                                 "duration": 1000,
                                                 "position": 500}))
        self.assertEqual(self.external, [PlaybackEvent.PAUSED])
        self.svc.resume()
        self.client.resume.assert_called_once_with("dev-1")
        self.bus.emit(Message("spotifyd.play", {"track_id": "aaa",
                                                "duration": 1000,
                                                "position": 500}))
        self.assertEqual(self.external,
                         [PlaybackEvent.PAUSED, PlaybackEvent.RESUMED])
        self.assertEqual(self.backend.get_track_length(), 1000)


class TestTrackTimes(unittest.TestCase):
    def setUp(self):
        with patch.object(ovos_media_plugin_spotify, "SpotifyClient"):
            self.backend = SpotifyOCPAudioService({"identifier": DEVICE},
                                                  bus=FakeBus())

    def test_nothing_plays(self):
        self.assertIsNone(self.backend.get_track_length())
        self.assertIsNone(self.backend.get_track_position())

    def test_unknown_length(self):
        self.backend.load_track(A)
        self.backend.hooks.preload_uri(A)
        self.assertEqual(self.backend.get_track_length(), -1)
        self.assertIsInstance(self.backend.get_track_position(), int)
        self.assertEqual(self.backend.get_track_length(), -1)

    def test_end_without_track_start(self):
        events = []
        self.backend.bind_event_reporter(
            lambda e, **d: events.append((e, d)))
        bus = self.backend.bus
        bus.emit(Message("spotifyd.load", {"track_id": "aaa", "position": 0}))
        bus.emit(Message("spotifyd.end_of_track", {}))
        self.assertEqual(events, [(PlaybackEvent.END_OF_MEDIA, {"uri": A})])


if __name__ == "__main__":
    unittest.main()
