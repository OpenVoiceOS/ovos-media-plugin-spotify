import time

from ovos_plugin_manager.templates.media import PlaybackEvent, RemoteAudioPlayerBackend
from ovos_utils.log import LOG

from ovos_media_plugin_spotify.spotify_client import SpotifyClient
from ovos_media_plugin_spotify.spotifyd import SpotifydHooks


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

    def __init__(self, config, bus=None):
        super().__init__(config, bus)
        self._now_playing = None
        self.spotify = SpotifyClient()
        self._paused = False
        self._last_sync_ts = 0
        self.device_name = self.config.get("identifier")  # device name in spotify
        self.hooks = SpotifydHooks(bus=self.bus,
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
        """The single end-of-track callback: reached from
        ``_wait_until_finished``'s inactivity poll (natural end, no stop()
        call from us) and from spotifyd's own "stop"/"end_of_track"
        notifications (spotifyd's session ended, either because we asked
        or because the track simply finished). ``report_track_end``
        resolves STOPPED vs END_OF_MEDIA on its own via the base class's
        ``_stop_requested`` flag, set by ``stop()`` - this is the only
        ``report_track_end`` call site in this backend."""
        if not uri:
            self.hooks.reset_metadata()
        ended_uri = uri or self._now_playing
        self._paused = False
        self._last_sync_ts = 0
        self._now_playing = None
        self.report_track_end(uri=ended_uri)

    def on_track_error(self, uri: str = ""):
        """``spotify.play()`` (the ask) itself raised - nothing was ever
        confirmed playing, so this is a plain ask failure, not an
        end-of-track callback: report ERROR directly instead of going
        through ``report_track_end``."""
        if not uri:
            self.hooks.reset_metadata()
        errored_uri = uri or self._now_playing
        self._paused = False
        self._last_sync_ts = 0
        self._now_playing = None
        self.report(PlaybackEvent.ERROR, uri=errored_uri,
                    error="spotify playback error")

    def play(self):
        self.hooks.preload_uri(self._now_playing)
        self.on_track_start()
        try:
            self.spotify.play([self._now_playing],
                              dev_id=self.device)
            self._wait_until_finished()
        except Exception:
            self.on_track_error()

    def _wait_until_finished(self):
        # pool spotify to see when the player becomes inactive
        while self._last_sync_ts > 0:
            time.sleep(2)
            for d in self.spotify.devices:
                if d["name"] == self.device_name and not d["is_active"]:
                    self.on_track_end()
                    return

    def _stop(self) -> bool:
        # there is no hard stop method - we can only ask spotify to pause.
        # This is a pure ask: it reports nothing itself. The base class's
        # stop() has already flagged _stop_requested before calling us, so
        # whichever end-of-track callback eventually fires (spotifyd's own
        # "stop"/"end_of_track" hook, or _wait_until_finished's inactivity
        # poll) reports STOPPED via report_track_end/on_track_end - the
        # single call site for that.
        try:
            self.spotify.pause(self.device)
        except Exception as e:
            # eg. NoSpotifyDevicesError when the target device isn't
            # currently reported as active by spotify (already
            # stopped/paused elsewhere) - see issue #14 ("can't stop
            # playing"). Report False; our own state resets once the
            # end-of-track callback fires, same as a successful pause.
            LOG.warning(f"failed to pause spotify device on stop: {e}")
            return False
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

    def get_track_length(self) -> int:
        """
        getting the duration of the audio in milliseconds
        """
        return self.hooks.get_track_length()

    def get_track_position(self) -> int:
        """
        get current position in milliseconds
        """
        return self.hooks.get_track_position()


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    spotify = SpotifyOCPAudioService({"identifier": 'miro-asustufgamingf15fx506hmfx506hm'}, bus=FakeBus())
    spotify.load_track("spotify:artist:3TOqt5oJwL9BE2NG9MEwDa")
    time.sleep(1)
    spotify.play()
    from ovos_utils import wait_for_exit_signal

    wait_for_exit_signal()
