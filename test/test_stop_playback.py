"""
Regression tests for https://github.com/OpenVoiceOS/ovos-media-plugin-spotify/issues/14
("can't stop playing").

Traced root cause: `SpotifyClient.validate_device_id(dev_id)` crashes with
an unhandled `AttributeError: 'NoneType' object has no attribute 'lower'`
whenever `dev_id` is `None` - which is exactly what `SpotifyOCPAudioService.device`
returns when the target spotifyd device isn't currently reported as an
*active* Spotify device (e.g. because playback was stopped/paused from
elsewhere, matching the issue's second symptom). Since
`SpotifyOCPAudioService.stop()` called `self.spotify.pause(self.device)`
with no exception handling, that crash propagated out of `stop()` and
`on_track_end()` (which resets `_last_sync_ts`/`_paused`) never ran,
leaving the backend believing it was still playing.
"""
import unittest
from unittest.mock import MagicMock, patch


class TestValidateDeviceId(unittest.TestCase):
    def _client(self, devices):
        from ovos_media_plugin_spotify.spotify_client import SpotifyClient
        c = SpotifyClient()
        c._SpotifyClient__device_list = devices
        c._SpotifyClient__devices_fetched = 1e15  # avoid refetch (network)
        c._spotify = MagicMock()  # so `self.spotify` truthy without OAuth
        return c

    def test_none_device_id_raises_no_spotify_devices_error_not_attributeerror(self):
        from ovos_media_plugin_spotify.spotify_client import NoSpotifyDevicesError
        c = self._client([{"id": "abc", "name": "OVOS", "type": "Speaker",
                            "is_active": False}])
        with self.assertRaises(NoSpotifyDevicesError):
            c.validate_device_id(None)

    def test_known_device_id_still_resolves(self):
        c = self._client([{"id": "abc", "name": "OVOS", "type": "Speaker",
                            "is_active": True}])
        self.assertEqual(c.validate_device_id("abc"), "abc")


class TestStopAlwaysResetsState(unittest.TestCase):
    def test_stop_never_raises_even_if_pause_raises_and_end_callback_still_resets_state(self):
        """_stop() must not crash when spotify.pause() raises (issue #14).
        Under the v2 contract, _stop() itself is a pure ask and does not
        reset state or report anything - that happens once the
        end-of-track callback (on_track_end) eventually fires, whether
        that is spotifyd's own notification or _wait_until_finished's
        inactivity poll. This still guarantees the backend never gets
        stuck believing it is playing forever, it just moves *when* the
        reset happens."""
        from ovos_media_plugin_spotify import SpotifyOCPAudioService
        from ovos_media_plugin_spotify.spotify_client import NoSpotifyDevicesError
        from ovos_utils.fakebus import FakeBus

        with patch("ovos_media_plugin_spotify.SpotifyClient"), \
             patch("ovos_media_plugin_spotify.SpotifydHooks"):
            svc = SpotifyOCPAudioService.__new__(SpotifyOCPAudioService)
            svc.spotify = MagicMock()
            svc.spotify.pause.side_effect = NoSpotifyDevicesError()
            svc.spotify.devices = []  # device property -> None, like a
                                       # spotifyd device not currently active
            svc.device_name = "OVOS"
            svc.hooks = MagicMock()
            svc.bus = FakeBus()
            svc.meta = {}
            svc._event_reporter = None
            svc._stop_requested = False
            svc._now_playing = "spotify:track:x"
            svc._last_sync_ts = 12345.0
            svc._paused = True

            # must not raise despite spotify.pause() failing
            self.assertIs(svc.stop(), False)

            # the end-of-track callback (spotifyd's own notification, or
            # _wait_until_finished's poll) always follows and resets state
            svc.on_track_end()

        self.assertEqual(svc._last_sync_ts, 0)
        self.assertFalse(svc._paused)
        self.assertIsNone(svc._now_playing)


if __name__ == '__main__':
    unittest.main()
