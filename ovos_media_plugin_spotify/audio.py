import time

from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_utils.log import LOG

from ovos_media_plugin_spotify.spotify_client import SpotifyClient
from ovos_media_plugin_spotify.spotifyd import SpotifydHooks


class SpotifyAudioService(AudioBackend):
    """
        Spotify Audio backend
    """

    def __init__(self, config, bus, name='spotify'):
        super().__init__(config, bus, name)
        self.spotify = SpotifyClient()
        self._paused = False
        self._last_sync_ts = 0
        self.device_name = self.config.get("identifier")  # device name in spotify
        self.hooks = SpotifydHooks(bus=self.bus,
                                   track_start_callback=self.on_track_start,
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

    def on_track_start(self, uri: str = ""):
        self._now_playing = uri or self._now_playing
        self._last_sync_ts = time.time()
        # Indicate to audio service which track is being played
        if self._track_start_callback:
            # TODO why is it None sometimes?
            if self._now_playing:
                self._track_start_callback(self._now_playing)

    def on_track_end(self, uri: str = ""):
        if not uri:
            self.hooks.reset_metadata()
        self._paused = False
        self._last_sync_ts = 0
        if self._track_start_callback:
            self._track_start_callback(None)

    def on_track_error(self, uri: str = ""):
        if not uri:
            self.hooks.reset_metadata()
        self._paused = False
        self._last_sync_ts = 0

    def play(self, repeat=False):
        self.hooks.preload_uri(self._now_playing)
        self.on_track_start()
        try:
            self.spotify.play([self._now_playing],
                              dev_id=self.device_name)
            self._wait_until_finished()
        except:
            self.on_track_error()

    def _wait_until_finished(self):
        # pool spotify to see when the player becomes inactive
        while self._last_sync_ts > 0:
            time.sleep(2)
            for d in self.spotify.devices:
                if d["name"] == self.device_name and not d["is_active"]:
                    self.on_track_end()
                    return

    def stop(self):
        # there is no hard stop method
        if not self._paused:
            self.spotify.pause(self.device_name)
            self.on_track_end()

    def pause(self):
        if self.spotify.is_playing(self.device_name):
            self._paused = True
            self.spotify.pause(self.device_name)

    def resume(self):
        if self._paused:
            self._paused = False
            self.spotify.resume(self.device_name)

    def next(self):
        self.spotify.next(self.device_name)

    def previous(self):
        self.spotify.previous(self.device_name)

    def lower_volume(self):
        if self.spotify.is_playing(self.device_name):
            self.spotify.volume(int(self.spotify.DEFAULT_VOLUME / 3))

    def restore_volume(self):
        if self.spotify.is_playing(self.device_name):
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

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds
          Args:
                milliseconds (int): number of milliseconds of final position
        """
        # Not available in this plugin


def load_service(base_config, bus):
    backends = base_config.get('backends', {})
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['spotify', 'ovos_spotify'] and
                backends[b].get('active', True)]
    instances = [SpotifyAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No Spotify backends have been configured")
    return instances
