import time

from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_utils.log import LOG

from ovos_media_plugin_spotify.spotify_client import SpotifyClient


class SpotifyAudioService(AudioBackend):
    """
        Spotify Audio backend
    """

    def __init__(self, config, bus, name='spotify'):
        super().__init__(config, bus)
        self.spotify = SpotifyClient()
        self._paused = False
        self.ts = 0
        self.device_name = self.config.get("identifier")  # device name in spotify

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

    def on_track_start(self):
        self.ts = time.time()
        # Indicate to audio service which track is being played
        if self._track_start_callback:
            self._track_start_callback(self._now_playing)

    def on_track_end(self):
        self._paused = False
        self.ts = 0
        if self._track_start_callback:
            self._track_start_callback(None)

    def on_track_error(self):
        self._paused = False
        self.ts = 0

    def play(self, repeat=False):
        self.on_track_start()
        try:
            self.spotify.play([self._now_playing],
                              dev_id=self.device)
            self._wait_until_finished()
        except:
            self.on_track_error()

    def _wait_until_finished(self):
        # pool spotify to see when the player becomes inactive
        while self.ts > 0:
            time.sleep(2)
            for d in self.spotify.devices:
                if d["name"] == self.device_name and not d["is_active"]:
                    self.on_track_end()
                    return

    def stop(self):
        # there is no hard stop method
        self.spotify.pause(self.device)
        self.on_track_end()

    def pause(self):
        if self.spotify.is_playing(self.device):
            self._paused = True
            self.spotify.pause(self.device)

    def resume(self):
        if self._paused:
            self._paused = False
            self.spotify.resume(self.device)

    def next(self):
        self.spotify.next(self.device)

    def previous(self):
        self.spotify.previous(self.device)

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
        # we only can estimate how much we already played as a minimum value
        return self.get_track_position()

    def get_track_position(self) -> int:
        """
        get current position in milliseconds
        """
        # approximate given timestamp of playback start
        if self.ts:
            return int((time.time() - self.ts) * 1000)
        return 0

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds
          Args:
                milliseconds (int): number of milliseconds of final position
        """
        # Not available in this plugin


def load_service(base_config, bus):
    backends = base_config.get('backends', [])
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['spotify', 'ovos_spotify'] and
                backends[b].get('active', True)]
    instances = [SpotifyAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No Spotify backends have been configured")
    return instances
