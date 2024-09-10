import time

from ovos_bus_client.message import Message
from ovos_plugin_manager.templates.media import AudioPlayerBackend
from ovos_utils.log import LOG

from ovos_media_plugin_spotify.spotify_client import SpotifyClient


class SpotifyOCPAudioService(AudioPlayerBackend):
    """
        Spotify Audio backend
    """

    def __init__(self, config, bus=None):
        super().__init__(config, bus)
        self.spotify = SpotifyClient()
        self._paused = False
        self._last_sync_ts = 0
        self._track_len = 0
        self._track_pos = 0
        self.device_name = self.config.get("identifier")  # device name in spotify

        self.bus.on("spotifyd.start", self.on_spotify_start)
        self.bus.on("spotifyd.play", self.on_spotify_play)
        self.bus.on("spotifyd.pause", self.on_spotify_pause)
        self.bus.on("spotifyd.stop", self.on_spotify_stop)
        self.bus.on("spotifyd.load", self.on_spotify_load)
        self.bus.on("spotifyd.end_of_track", self.on_spotify_end)
        self.bus.on("spotifyd.change", self.on_spotify_change)
        self.bus.on("spotifyd.preloading", self.on_spotify_preloading)

    ##################
    # spotifyd hooks
    def on_spotify_start(self, message: Message):
        self._last_sync_ts = time.time()
        self._now_playing = "spotify:track:" + message.data["track_id"]
        self._track_pos = message.data["position"]  # milliseconds
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 2}))  # loading media

    def on_spotify_play(self, message: Message):
        self._last_sync_ts = time.time()
        self._now_playing = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds

        self.on_track_start()
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 1}))  # playing
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 6}))  # buffered media

    def on_spotify_stop(self, message: Message):
        self._now_playing = None
        self._track_len = 0
        self._track_pos = 0
        self._last_sync_ts = 0
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 1}))  # no media
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 0}))  # stopped

    def on_spotify_pause(self, message: Message):
        self._now_playing = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        self._last_sync_ts = 0
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused

    def on_spotify_load(self, message: Message):
        self._last_sync_ts = time.time()
        self._track_pos = message.data["position"]  # milliseconds
        self._now_playing = "spotify:track:" + message.data["track_id"]

    def on_spotify_preloading(self, message: Message):
        # when track is about to end we get info about next song
        # we could show a "coming up next" popup
        pass

    def on_spotify_end(self, message: Message):
        self._track_pos = self._track_len
        self.on_track_end()
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 7}))  # end of media

    def on_spotify_change(self, message: Message):
        self._now_playing = "spotify:track:" + message.data["track_id"]
        self._last_sync_ts = time.time()
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 2}))  # loading media

    #################
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
        self._last_sync_ts = time.time()
        # Indicate to audio service which track is being played
        if self._track_start_callback:
            self._track_start_callback(self._now_playing)

    def on_track_end(self):
        self._paused = False
        self._last_sync_ts = 0
        if self._track_start_callback:
            self._track_start_callback(None)

    def on_track_error(self):
        self._paused = False
        self._last_sync_ts = 0
        self.ocp_error()

    def play(self):
        self.on_track_start()
        try:
            self.spotify.play([self._now_playing],
                              dev_id=self.device)
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
        return self._track_len or self.get_track_position()

    def get_track_position(self) -> int:
        """
        get current position in milliseconds
        """
        pos = self._track_pos or 0
        if self._last_sync_ts:  # add the elapsed time since last update of self._track_pos
            pos += (time.time() - self._last_sync_ts) * 1000
        if not self._track_len:
            self._track_len = pos
        return min(pos, self._track_len)

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds
          Args:
                milliseconds (int): number of milliseconds of final position
        """
        # Not available in this plugin


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    spotify = SpotifyOCPAudioService({"identifier": 'miro-asustufgamingf15fx506hmfx506hm'}, bus=FakeBus())
    spotify.load_track("spotify:artist:3TOqt5oJwL9BE2NG9MEwDa")
    time.sleep(1)
    spotify.play()
    from ovos_utils import wait_for_exit_signal

    wait_for_exit_signal()
