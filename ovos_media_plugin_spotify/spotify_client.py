import time

import requests
import spotipy
from ovos_backend_client.api import OAuthApi
from ovos_utils import flatten_list
from ovos_utils.log import LOG
from requests.exceptions import HTTPError
from spotipy.oauth2 import SpotifyAuthBase


class NoSpotifyDevicesError(Exception):
    pass


class PlaylistNotFoundError(Exception):
    pass


class SpotifyNotAuthorizedError(Exception):
    pass


OAUTH_TOKEN_ID = "ocp_spotify"


class OVOSSpotifyCredentials(SpotifyAuthBase):
    """ Oauth through ovos-backend-client"""

    def __init__(self):
        super().__init__(requests.Session())

    @staticmethod
    def get_access_token():
        t = OAuthApi().get_oauth_token(OAUTH_TOKEN_ID,
                                       auto_refresh=True)
        return t["access_token"]


class SpotifyClient:
    def __init__(self):
        self._spotify = None
        self.dev_id = None

        self.__device_list = None
        self.__devices_fetched = 0
        self.DEFAULT_VOLUME = 90

    @property
    def spotify(self):
        if self._spotify is None:
            self.load_credentials()
        return self._spotify

    def is_playing(self, dev_id=None):
        """ Get playback state, either across Spotify or for given device.
        Args:
            device (int): device id to check, if None playback on any device
                          will be reported.
        Returns:
            True if specified device is playing
        """
        if self.spotify:
            try:
                status = self.spotify.current_user_playing_track()
                if not status['is_playing'] or dev_id is None:
                    return status['is_playing']

                # Verify it is playing on the given device
                dev = self.get_device(dev_id)
                return dev and dev['is_active']
            except:
                # Technically a 204 return from status() request means 'no track'
                return False  # assume not playing
        return False

    def next(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.next_track(dev_id)

    def previous(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.previous_track(dev_id)

    def pause(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.pause_playback(dev_id)

    def resume(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.start_playback(dev_id)

    def volume(self, volume, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.volume(volume, dev_id)

    def load_credentials(self):
        """ Retrieve credentials from the backend and connect to Spotify """
        try:
            creds = OVOSSpotifyCredentials()
            self._spotify = spotipy.Spotify(client_credentials_manager=creds)
        except(HTTPError, SpotifyNotAuthorizedError):
            LOG.error('Couldn\'t fetch spotify credentials')

    @property
    def devices(self):
        """ Devices, cached for 60 seconds """
        if not self.spotify:
            return []  # No connection, no devices
        now = time.time()
        if not self.__device_list or (now - self.__devices_fetched > 60):
            self.__device_list = self.spotify.devices().get('devices', [])
            self.__devices_fetched = now
        return self.__device_list

    def validate_device_id(self, dev_id):
        found = False
        for d in self.devices:
            if d["id"] == dev_id:
                found = True
                break
        if not found:
            for d in self.devices:
                if d["name"].lower() == dev_id.lower():
                    dev_id = d["id"]
                    found = True
                    break
        if not found:
            for d in self.devices:
                if d["type"].lower() == dev_id.lower():
                    dev_id = d["id"]
                    break
        if dev_id is None:
            raise NoSpotifyDevicesError
        return dev_id

    def get_device(self, dev_id):
        for d in self.devices:
            if d["id"] == dev_id:
                return d
        return None

    def play(self, uris=None, dev_id=None, context_uri=None):
        """ Start spotify playback and log any exceptions. """
        if isinstance(uris, str) and uris.startswith("spotify:playlist:"):
            return self.start_playlist_playback(uris, dev_id=dev_id)

        dev_id = self.validate_device_id(dev_id)

        if context_uri is None:
            if not isinstance(uris, list):
                uris = [uris]

            for idx, uri in enumerate(uris):
                if uri.startswith("spotify:playlist:"):
                    uris[idx] = ["spotify:track:" + t["track"]["id"] for t in self.tracks_from_playlist(uri)]
                elif uri.startswith("spotify:artist:"):
                    uris[idx] = ["spotify:track:" + t["id"] for t in self.tracks_from_artist(uri)]
                elif uri.startswith("spotify:album:"):
                    uris[idx] = ["spotify:track:" + t["id"] for t in self.tracks_from_album(uri)]

            uris = flatten_list(uris)

        try:
            LOG.info(f'spotify_play: {dev_id}')
            self.spotify.start_playback(device_id=dev_id, uris=uris, context_uri=context_uri)

            self.dev_id = dev_id
        except spotipy.SpotifyException as e:
            # TODO: Catch other conditions?
            if e.http_status == 403:
                LOG.error(f'Play command returned 403, play is likely already in progress. \n {e}')
            else:
                raise SpotifyNotAuthorizedError from e
        except Exception as e:
            LOG.exception(e)
            raise

    def start_playlist_playback(self, uri, name="playlist", dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        dev = self.get_device(dev_id)
        name = name.replace('|', ':')
        if uri:
            LOG.info(u'playing {} using {}'.format(name, dev['name']))
            self.play(dev_id=dev_id, context_uri=uri)
        else:
            LOG.info('No playlist found')
            raise PlaylistNotFoundError

    def tracks_from_playlist(self, playlist_id):
        playlist_id = playlist_id.replace("spotify:playlist:", "")
        return self.spotify.playlist_tracks(playlist_id)

    def tracks_from_artist(self, artist_id):
        # get top tracks
        # spotify:artist:3TOqt5oJwL9BE2NG9MEwDa
        top_tracks = self.spotify.artist_top_tracks(artist_id)
        return [t for t in top_tracks["tracks"]]

    def tracks_from_album(self, artist_id):
        # get top tracks
        # spotify:artist:3TOqt5oJwL9BE2NG9MEwDa
        top_tracks = self.spotify.album_tracks(artist_id)
        return [t for t in top_tracks["items"]]

    def track_info(self):
        """ Extract info of current track. """
        status = self.spotify.current_user_playing_track()
        try:
            artist = status['item']['artists'][0]['name']
        except Exception:
            artist = 'unknown'
        try:
            track = status['item']['name']
        except Exception:
            track = 'unknown'
        try:
            album = status['item']['album']['name']
        except Exception:
            album = 'unknown'
        return {"album": album,
                "artist": artist,
                "title": track}


if __name__ == "__main__":
    spotify = SpotifyClient()
    for d in spotify.devices:
        print(d)
    spotify.play('spotify:artist:3TOqt5oJwL9BE2NG9MEwDa',
                 dev_id='0fdb28980e72b082982e1adf8d197e9214d7ee6a')
