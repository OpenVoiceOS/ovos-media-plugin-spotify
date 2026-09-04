import time

from ovos_bus_client.message import Message


class SpotifydHooks:
    """Listens to spotifyd's own bus notifications (a plugin-private,
    non-OCP protocol - spotifyd forwards physical player events for the
    Spotify Connect device it drives) and turns them into callbacks the
    backend can ``report()`` upward as ``PlaybackEvent``s.

    This class never emits ``ovos.common_play.*`` itself - only the
    daemon that owns the backend does that, based on the physical events
    the backend reports. ``self.bus`` here is used purely to *receive*
    spotifyd's notifications.
    """

    def __init__(self, bus,
                 track_start_callback=None,
                 track_pause_callback=None,
                 track_resume_callback=None,
                 track_end_callback=None,
                 track_error_callback=None):
        self.current_uri = None
        self._last_sync_ts = 0
        self._track_len = 0
        self._track_pos = 0
        self.bus = bus

        self.track_start_callback = track_start_callback
        self.track_pause_callback = track_pause_callback
        self.track_resume_callback = track_resume_callback
        # both spotifyd's "stop" (session ended) and "end_of_track" (track
        # finished) notifications land on the same end-of-track callback -
        # the backend's on_track_end is the single report_track_end call
        # site and resolves STOPPED vs END_OF_MEDIA itself via the base
        # class's _stop_requested flag, so this class does not need to
        # (and must not) tell the two apart
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
    # spotifyd hooks - these fire from spotifyd's own event stream, i.e.
    # they can reflect state changes the user made outside of us (the
    # Spotify app, another Connect client, physical hardware buttons).
    # They are real physical events, not messagebus state to forward.
    def on_spotify_start(self, message: Message):
        self._last_sync_ts = time.time()
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_pos = message.data["position"]  # milliseconds

    def on_spotify_play(self, message: Message):
        # spotifyd fires "play" both when a new track starts and when a
        # paused track resumes; the track id tells them apart since we
        # never get an explicit "resume" notification from spotifyd
        new_uri = "spotify:track:" + message.data["track_id"]
        is_resume = new_uri == self.current_uri
        self._last_sync_ts = time.time()
        self.current_uri = new_uri
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        if is_resume and self.track_resume_callback is not None:
            self.track_resume_callback(self.current_uri)
        elif not is_resume and self.track_start_callback is not None:
            self.track_start_callback(self.current_uri)

    def on_spotify_stop(self, message: Message):
        stopped_uri = self.current_uri
        self.current_uri = None
        self._track_len = 0
        self._track_pos = 0
        self._last_sync_ts = 0
        if self.track_end_callback is not None:
            self.track_end_callback(stopped_uri)

    def on_spotify_pause(self, message: Message):
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._track_len = message.data["duration"]  # milliseconds
        self._track_pos = message.data["position"]  # milliseconds
        self._last_sync_ts = 0
        if self.track_pause_callback is not None:
            self.track_pause_callback(self.current_uri)

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
        ended_uri = self.current_uri
        if self.track_end_callback is not None:
            self.track_end_callback(ended_uri)

    def on_spotify_change(self, message: Message):
        # a new track started playing (e.g. skip triggered outside of us)
        self.current_uri = "spotify:track:" + message.data["track_id"]
        self._last_sync_ts = time.time()
        if self.track_start_callback is not None:
            self.track_start_callback(self.current_uri)
