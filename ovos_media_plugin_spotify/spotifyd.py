import time

from ovos_bus_client.message import Message


class SpotifydHooks:
    def __init__(self, bus,
                 track_start_callback=None,
                 track_end_callback=None,
                 track_error_callback=None):
        self.current_uri = None
        self._last_sync_ts = 0
        self._track_len = 0
        self._track_pos = 0
        self.bus = bus

        self.track_start_callback = track_start_callback
        self.track_end_callback = track_end_callback
        self.track_error_callback = track_error_callback

        self.bus.on("spotifyd.start", self.on_spotify_start)
        self.bus.on("spotifyd.play", self.on_spotify_play)
        self.bus.on("spotifyd.pause", self.on_spotify_pause)
        self.bus.on("spotifyd.stop", self.on_spotify_stop)
        self.bus.on("spotifyd.load", self.on_spotify_load)
        self.bus.on("spotifyd.end_of_track", self.on_spotify_end)
        self.bus.on("spotifyd.change", self.on_spotify_change)
        self.bus.on("spotifyd.preloading", self.on_spotify_preloading)

    def reset_metadata(self):
        self.current_uri = None
        self._last_sync_ts = 0
        self._track_len = 0
        self._track_pos = 0

    def preload_uri(self, uri: str):
        self.reset_metadata()
        self.current_uri = uri
        self._last_sync_ts = time.time()

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

    ##################
    # spotifyd hooks
    def on_spotify_start(self, message: Message):
        self._last_sync_ts = time.time()
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_pos = message.data["position"]  # milliseconds
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 2}))  # loading media

    def on_spotify_play(self, message: Message):
        self._last_sync_ts = time.time()
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 1}))  # playing
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 6}))  # buffered media
        if self.track_start_callback is not None:
            self.track_start_callback(self.current_uri)

    def on_spotify_stop(self, message: Message):
        self.current_uri = None
        self._track_len = 0
        self._track_pos = 0
        self._last_sync_ts = 0
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 1}))  # no media
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 0}))  # stopped

    def on_spotify_pause(self, message: Message):
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        self._last_sync_ts = 0
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused

    def on_spotify_load(self, message: Message):
        self._last_sync_ts = time.time()
        self._track_pos = message.data["position"]  # milliseconds
        self.current_uri = "spotify:track:" + message.data["track_id"]

    def on_spotify_preloading(self, message: Message):
        # when track is about to end we get info about next song
        # we could show a "coming up next" popup
        pass

    def on_spotify_end(self, message: Message):
        self._track_pos = self._track_len
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 7}))  # end of media
        if self.track_end_callback is not None:
            self.track_end_callback(self.current_uri)

    def on_spotify_change(self, message: Message):
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._last_sync_ts = time.time()
        self.bus.emit(message.forward("ovos.common_play.player.state",
                                      {"state": 2}))  # paused
        self.bus.emit(message.forward("ovos.common_play.media.state",
                                      {"state": 2}))  # loading media


class SpotifydEvents(SpotifydHooks):
    """spotifyd listener for the MediaBackend v2 class.

    It emits no ``ovos.common_play.*`` messages: the backend reports each
    callback as a ``PlaybackEvent`` and ovos-media emits the bus state.
    The parent class keeps the legacy audio service behaviour.
    """

    def __init__(self, bus,
                 track_start_callback=None,
                 track_pause_callback=None,
                 track_resume_callback=None,
                 track_end_callback=None,
                 track_error_callback=None):
        self.track_pause_callback = track_pause_callback
        self.track_resume_callback = track_resume_callback
        super().__init__(bus, track_start_callback=track_start_callback,
                         track_end_callback=track_end_callback,
                         track_error_callback=track_error_callback)

    def on_spotify_start(self, message: Message):
        self._last_sync_ts = time.time()
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_pos = message.data["position"]  # milliseconds

    def on_spotify_play(self, message: Message):
        # spotifyd sends "play" for a new track and for a resume;
        # only the track id tells them apart
        new_uri = "spotify:track:" + message.data["track_id"]
        is_resume = new_uri == self.current_uri
        self._last_sync_ts = time.time()
        self.current_uri = new_uri
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        if is_resume and self.track_resume_callback is not None:
            self.track_resume_callback(new_uri)
        elif not is_resume and self.track_start_callback is not None:
            self.track_start_callback(new_uri)

    def on_spotify_stop(self, message: Message):
        stopped_uri = self.current_uri
        self.reset_metadata()
        if self.track_end_callback is not None:
            self.track_end_callback(stopped_uri)

    def on_spotify_pause(self, message: Message):
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        self._last_sync_ts = 0
        if self.track_pause_callback is not None:
            self.track_pause_callback(self.current_uri)

    def on_spotify_end(self, message: Message):
        self._track_pos = self._track_len
        if self.track_end_callback is not None:
            self.track_end_callback(self.current_uri)

    def on_spotify_change(self, message: Message):
        # a track started outside of us, eg. a skip in the Spotify app
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._last_sync_ts = time.time()
        if self.track_start_callback is not None:
            self.track_start_callback(self.current_uri)
