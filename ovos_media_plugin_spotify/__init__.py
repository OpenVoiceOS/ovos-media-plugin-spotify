import threading
import time
from typing import Optional

from ovos_plugin_manager.templates.media import PlaybackEvent, RemoteAudioPlayerBackend
from ovos_utils.log import LOG

from ovos_media_plugin_spotify.spotify_client import SpotifyClient
from ovos_media_plugin_spotify.spotifyd import SpotifydEvents


class SpotifyOCPAudioService(RemoteAudioPlayerBackend):
    """
        Spotify Audio backend

        This is a remote player: it drives playback on a Spotify Connect
        device, not a local decoder. Anything that happens on that device
        from outside of us (the Spotify app, another Connect client, a
        physical remote) is a real state change we learn about only
        through ``SpotifydHooks`` and must report just like our own
        actions.
    """

    can_seek = False  # SpotifyClient/spotifyd never implemented seeking
    can_pause = True
    poll_interval = 2  # seconds between device activity polls

    def __init__(self, config, bus=None):
        super().__init__(config, bus)
        self._now_playing = None
        self.spotify = SpotifyClient()
        self._paused = False
        self._last_sync_ts = 0
        self._poll_id = 0  # a poll thread runs while its id is current
        self.device_name = self.config.get("identifier")  # device name in spotify
        self.hooks = SpotifydEvents(bus=self.bus,
                                   track_start_callback=self.on_track_start,
                                   track_pause_callback=self.on_track_pause,
                                   track_resume_callback=self.on_track_resume,
                                   track_end_callback=self.on_track_end,
                                   track_error_callback=self.on_track_error)

    @property
    def device(self):
        for d in self.spotify.devices:
            if d["name"] == self.device_name:
                return d["id"]
        return None

    def supported_uris(self):
        names = [d["name"] for d in self.spotify.devices]
        if self.device_name not in names:
            LOG.warning(f"{self.device_name} not found in spotify devices: {names}")
            return []
        return ['spotify']

    def load_track(self, uri: str, metadata: dict = None) -> bool:
        self._now_playing = uri
        self.meta.update(metadata or {})
        LOG.debug(f"queuing for {self.__class__.__name__} playback: {uri}")
        return True

    def on_track_start(self, uri: str = ""):
        self._now_playing = uri or self._now_playing
        self._last_sync_ts = time.time()
        self._paused = False
        if self._now_playing:
            self.report(PlaybackEvent.TRACK_START, uri=self._now_playing)

    def on_track_pause(self, uri: str = ""):
        """Status-listener report: spotifyd told us the Connect device
        paused. ``pause()`` itself is a pure ask (per the v2 remote-backend
        contract) and never reports - this is the sole path that reports
        PAUSED, whether the pause was ours or made from the Spotify app."""
        if not self._paused:
            self._paused = True
            self.report(PlaybackEvent.PAUSED, uri=uri or self._now_playing)

    def on_track_resume(self, uri: str = ""):
        """Status-listener report, see on_track_pause."""
        if self._paused:
            self._paused = False
            self.report(PlaybackEvent.RESUMED, uri=uri or self._now_playing)

    def on_track_end(self, uri: str = ""):
        """Report the end of *uri*, or of the current track.

        spotifyd's "stop" and "end_of_track" and the inactivity poll all
        land here. An end of a replaced track keeps the state of the track
        that replaced it. An end after ``stop()`` has no track and reports
        nothing: ovos-media reports the stop itself.
        """
        ended_uri = uri or self._now_playing
        if ended_uri is None:
            return
        if ended_uri == self._now_playing:
            self.hooks.reset_metadata()
            self._paused = False
            self._last_sync_ts = 0
            self._now_playing = None
        self.report_track_end(uri=ended_uri)

    def on_track_error(self, uri: str = ""):
        """``spotify.play()`` raised: nothing played, so report ERROR."""
        errored_uri = uri or self._now_playing
        if errored_uri == self._now_playing:
            self.hooks.reset_metadata()
            self._paused = False
            self._last_sync_ts = 0
            self._now_playing = None
        self.report(PlaybackEvent.ERROR, uri=errored_uri,
                    error="spotify playback error")

    def play(self):
        uri = self._now_playing
        if not uri:
            LOG.warning("play() called with no track loaded")
            return
        self.hooks.preload_uri(uri)
        self.on_track_start()
        try:
            self.spotify.play([uri], dev_id=self.device)
        except Exception:
            self.on_track_error(uri)
            return
        # ovos-media calls play() on its dispatcher; it must not block
        self._poll_id += 1
        threading.Thread(target=self._wait_until_finished,
                         args=(uri, self._poll_id), daemon=True).start()

    def _polling(self, uri: str, poll_id: int) -> bool:
        return (poll_id == self._poll_id and self._last_sync_ts > 0
                and self._now_playing == uri)

    def _wait_until_finished(self, uri: str, poll_id: int):
        # poll spotify to see when the player becomes inactive
        while self._polling(uri, poll_id):
            time.sleep(self.poll_interval)
            if not self._polling(uri, poll_id):
                return
            for d in self.spotify.devices:
                if d["name"] == self.device_name and not d["is_active"]:
                    self.on_track_end(uri)
                    return

    def _stop(self) -> bool:
        # There is no hard stop: ask spotify to pause. spotifyd answers
        # with "pause", not "stop", so no end callback follows. Clear the
        # track state here, which also ends the poll thread.
        try:
            self.spotify.pause(self.device)
        except Exception as e:
            # eg. NoSpotifyDevicesError when the device is not active,
            # see issue #14 ("can't stop playing")
            LOG.warning(f"failed to pause spotify device on stop: {e}")
            return False
        finally:
            self._poll_id += 1
            self.hooks.reset_metadata()
            self._paused = False
            self._last_sync_ts = 0
            self._now_playing = None
            self._stop_requested = False
        return True

    def pause(self):
        # pure ask (v2 remote-backend contract): reports nothing. The
        # spotifyd pause hook (on_track_pause) is the sole reporter of the
        # resulting PAUSED transition, exactly as it would be for a pause
        # triggered from the Spotify app itself.
        if self.spotify.is_playing(self.device):
            self.spotify.pause(self.device)

    def resume(self):
        # pure ask - see pause(); on_track_resume reports RESUMED once
        # spotifyd confirms the transition.
        if self._paused:
            self.spotify.resume(self.device)

    def lower_volume(self):
        if self.spotify.is_playing(self.device):
            self.spotify.volume(int(self.spotify.DEFAULT_VOLUME / 3))

    def restore_volume(self):
        if self.spotify.is_playing(self.device):
            self.spotify.volume(int(self.spotify.DEFAULT_VOLUME))

    def track_info(self):
        """ Extract info of current track. """
        return self.spotify.track_info()

    def get_track_length(self) -> Optional[int]:
        """Duration in milliseconds, None if nothing plays, -1 if unknown."""
        if self._now_playing is None:
            return None
        return self.hooks._track_len or -1

    def get_track_position(self) -> Optional[int]:
        """Position in milliseconds, None if nothing plays."""
        if self._now_playing is None:
            return None
        pos = self.hooks._track_pos or 0
        if self.hooks._last_sync_ts:
            pos += (time.time() - self.hooks._last_sync_ts) * 1000
        if self.hooks._track_len:
            pos = min(pos, self.hooks._track_len)
        return int(pos)


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    spotify = SpotifyOCPAudioService({"identifier": 'miro-asustufgamingf15fx506hmfx506hm'}, bus=FakeBus())
    spotify.load_track("spotify:artist:3TOqt5oJwL9BE2NG9MEwDa")
    time.sleep(1)
    spotify.play()
    from ovos_utils import wait_for_exit_signal

    wait_for_exit_signal()
