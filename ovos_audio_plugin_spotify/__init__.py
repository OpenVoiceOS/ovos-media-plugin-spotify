from ovos_utils.log import LOG
from ovos_audio_plugin_spotify.spotify_client import SpotifyClient
from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_backend_client.api import DeviceApi


class SpotifyAudioService(AudioBackend):
    """
        Spotify Audio backend
    """

    def __init__(self, config, bus, name='spotify'):
        super().__init__(config, bus)
        self.config = config
        self.bus = bus
        self.name = name
        self.tracks = []
        self.spotify = SpotifyClient()
        self._paused = False

    def maybe_launch_librespot(self, device_name):
        # TODO
        # #!/bin/bash
        #
        # if [[ -f /var/log/spotify/librespot.log ]]; then
        #     rm /var/log/spotify/librespot.log
        # fi
        #
        #
        # /opt/spotify/librespot --name $DEVICE_NAME \
        # --bitrate 160 \
        # --disable-audio-cache \
        # --enable-volume-normalisation \
        # --initial-volume=100 \
        # --verbose \
        # --username $USER \
        # --password $PSWD >> /var/log/spotify/librespot.log 2>&1
        # ```
        self.spotify.device_name = f"ovos-{DeviceApi().identity.uuid}"  # TODO - from config / set in librespot too

    @property
    def device(self):
        return self.spotify.device_name

    def supported_uris(self):
        return ['spotify']

    def clear_list(self):
        self.tracks = []
        # TODO remove from spotify queue
        # Not available https://github.com/spotify/web-api/issues/462
        # once playback is started calling this will have no effect

    def add_list(self, tracks):
        self.tracks += tracks
        LOG.info("Track list is " + str(tracks))

    def play(self, repeat=False):
        # TODO handle choose device (config / utterance ?)
        self.spotify.play(self.tracks, dev_id=self.device, repeat=repeat)

    def stop(self):
        # there is no hard stop method
        self.spotify.pause(self.device)

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

    def track_start(self, data, other):
        if self._track_start_callback:
            self._track_start_callback(self.track_info()['name'])


def load_service(base_config, bus):
    backends = base_config.get('backends', [])
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') == 'spotify' and
                backends[b].get('active', True)]
    instances = [SpotifyAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No Spotify backends have been configured")
    return instances
