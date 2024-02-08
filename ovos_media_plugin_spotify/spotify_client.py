import time
from functools import wraps

import requests
import spotipy
from ovos_backend_client.api import OAuthApi
from ovos_utils import flatten_list
from ovos_utils.log import LOG
from requests.exceptions import HTTPError
from spotipy.oauth2 import SpotifyAuthBase


class SpotifyPlaybackError(Exception):
    pass


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
        self.access_token = None
        self.expiration_time = None
        self.get_access_token()

    @staticmethod
    def get_token():
        """ Get token with a single retry."""
        retry = False
        d = None
        try:
            d = OAuthApi().get_oauth_token(OAUTH_TOKEN_ID)
        except HTTPError as e:
            if e.response.status_code == 404:  # Token doesn't exist
                raise SpotifyNotAuthorizedError
            if e.response.status_code == 401:  # Device isn't paired
                raise SpotifyNotAuthorizedError
            else:
                retry = True
        if retry:
            d = OAuthApi().get_oauth_token(OAUTH_TOKEN_ID)
        if not d:
            raise SpotifyNotAuthorizedError
        return d

    def get_access_token(self, force=False):
        if (not self.access_token or time.time() > self.expiration_time or force):
            d = self.get_token()
            self.access_token = d['access_token']
            # get expiration time from message, if missing assume 1 hour
            self.expiration_time = d.get('expiration') or time.time() + 3600
        return self.access_token


def refresh_spotify_oauth(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 401:
                self.client_credentials_manager.get_access_token(force=True)
                return func(self, *args, **kwargs)
            else:
                raise

    return wrapper


class SpotifyConnect(spotipy.Spotify):
    """ Implement the Spotify Connect API.
    See:  https://developer.spotify.com/web-api/
    This class extends the spotipy.Spotify class with the refresh_auth decorator
    """

    @staticmethod
    def get_album_info(data):
        """ Get album info from data object.
        Arguments:
            data: data structure from spotify
        Returns: tuple with name, [artists], uri)
        """
        return (data['albums']['items'][0]['name'],
                [a['name'] for a in data['albums']['items'][0]['artists']],
                data['albums']['items'][0]['uri'])

    @staticmethod
    def get_artist_info(data):
        """ Get artist info from data object.
        Arguments:
            data: data structure from spotify
        Returns: tuple with name, uri)
        """
        return (data['artists']['items'][0]['name'],
                data['artists']['items'][0]['uri'])

    @staticmethod
    def get_song_info(data):
        """ Get song info from data object.
        Arguments:
            data: data structure from spotify
        Returns: tuple with name, [artists], uri)
        """
        return (data['tracks']['items'][0]['name'],
                [a['name'] for a in data['tracks']['items'][0]['artists']],
                data['tracks']['items'][0]['uri'])

    @staticmethod
    def status_info(status):
        """ Return track, artist, album tuple from spotify status.
            Arguments:
                status (dict): Spotify status info
            Returns:
                tuple (track, artist, album)
         """
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
        return track, artist, album

    @refresh_spotify_oauth
    def get_devices(self):
        """ Get a list of Spotify devices from the API.
        Returns:
            list of spotify devices connected to the user.
        """
        # TODO: Cache for a brief time
        devices = self.devices()
        return devices.get('devices', [])

    def get_device(self, dev_id):
        for d in self.get_devices():
            if d["id"] == dev_id:
                return d
        return None

    @refresh_spotify_oauth
    def status(self):
        """ Get current playback status (across the Spotify system) """
        return self.current_user_playing_track()

    @refresh_spotify_oauth
    def is_playing(self, device=None):
        """ Get playback state, either across Spotify or for given device.
        Args:
            device (int): device id to check, if None playback on any device
                          will be reported.
        Returns:
            True if specified device is playing
        """
        try:
            status = self.status()
            if not status['is_playing'] or device is None:
                return status['is_playing']

            # Verify it is playing on the given device
            dev = self.get_device(device)
            return dev and dev['is_active']
        except:
            # Technically a 204 return from status() request means 'no track'
            return False  # assume not playing

    @refresh_spotify_oauth
    def transfer_playback(self, device_id, force_play=True):
        """ Transfer playback to another device.
        Arguments:
            device_id (int):      transfer playback to this device
            force_play (boolean): true if playback should start after
                                  transfer
        """
        super().transfer_playback(device_id=device_id, force_play=force_play)

    @refresh_spotify_oauth
    def play(self, device, uris=None, context_uri=None):
        """ Start playback of tracks, albums or artist.
        Can play either a list of uris or a context_uri for things like
        artists and albums. Both uris and context_uri shouldn't be provided
        at the same time.
        Args:
            device (int):      device id to start playback on
            uris (list):       list of track uris to play
            context_uri (str): Spotify context uri for playing albums or
                               artists.
        """
        self.start_playback(device_id=device, uris=uris, context_uri=context_uri)

    @refresh_spotify_oauth
    def pause(self, device):
        """ Pause user's playback on device.
        Arguments:
            device_id: device to pause
        """
        self.pause_playback(device_id=device)

    @refresh_spotify_oauth
    def next(self, device):
        """ Skip track.
        Arguments:
            device_id: device id for playback
        """
        self.next_track(device_id=device)

    @refresh_spotify_oauth
    def prev(self, device):
        """ Move back in playlist.
        Arguments
            device_id: device target for playback
        """
        self.previous_track(device_id=device)

    @refresh_spotify_oauth
    def volume(self, device, volume):
        """ Set volume of device:
        Parameters:
            device: device id
            volume: volume in percent
        """
        super().volume(volume_percent=volume, device_id=device)

    @refresh_spotify_oauth
    def shuffle(self, state):
        """ Toggle shuffling
            Parameters:
                state: Shuffle state
        """
        super().shuffle(state)  # TODO pass device_id

    @refresh_spotify_oauth
    def repeat(self, state):
        """ Toggle repeat
        state:
            track - will repeat the current track.
            context - will repeat the current context.
            off - will turn repeat off.

            Parameters:
                state: Shuffle state
        """
        super().repeat(state)  # TODO pass device_id


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
        if self.spotify:
            return self.spotify.is_playing(dev_id)
        return False

    def next(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.next(dev_id)

    def previous(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.prev(dev_id)

    def pause(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.pause(dev_id)

    def resume(self, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.play(dev_id)

    def volume(self, volume, dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        return self.spotify.volume(dev_id, volume)

    def load_credentials(self):
        """ Retrieve credentials from the backend and connect to Spotify """
        try:
            creds = OVOSSpotifyCredentials()
            self._spotify = SpotifyConnect(client_credentials_manager=creds)
        except(HTTPError, SpotifyNotAuthorizedError):
            LOG.error('Couldn\'t fetch spotify credentials')

    @property
    def devices(self):
        """ Devices, cached for 60 seconds """
        if not self.spotify:
            return []  # No connection, no devices
        now = time.time()
        if not self.__device_list or (now - self.__devices_fetched > 60):
            self.__device_list = self.spotify.get_devices()
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
            LOG.info(u'spotify_play: {}'.format(dev_id))
            self.spotify.play(dev_id, uris=uris, context_uri=context_uri)
            self.dev_id = dev_id
        except spotipy.SpotifyException as e:
            # TODO: Catch other conditions?
            if e.http_status == 403:
                LOG.error('Play command returned 403, play is likely '
                               'already in progress. \n {}'.format(repr(e)))
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
        ret = {}
        track, artist, album = self.spotify.status_info(self.spotify.status())
        ret['album'] = album
        ret['artists'] = artist
        ret['name'] = track
        return ret


if __name__ == "__main__":
    spotify = SpotifyClient()
    for d in spotify.devices:
        print(d)
    spotify.play('spotify:artist:3TOqt5oJwL9BE2NG9MEwDa',
                 dev_id='0fdb28980e72b082982e1adf8d197e9214d7ee6a')
