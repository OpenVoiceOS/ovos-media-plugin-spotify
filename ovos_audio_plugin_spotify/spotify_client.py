import re
import time

import requests
import spotipy

from functools import wraps

from ovos_backend_client.api import OAuthApi, DeviceApi
from ovos_utils import flatten_list
from ovos_utils.log import LOG
from ovos_utils.parse import match_one, fuzzy_match
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

OAUTH_TOKEN_ID = "audioplugin_spotify"

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
    # Return value definition indication nothing was found
    # (confidence None, data None)
    NOTHING_FOUND = (None, 0.0)
    # Confidence levels for generic play handling
    DIRECT_RESPONSE_CONFIDENCE = 0.8

    MATCH_CONFIDENCE = 0.5

    def __init__(self):
        self.index = 0
        self._spotify = None
        self.process = None
        self.device_name = None
        self.dev_id = None
        self.idle_count = 0
        self.is_player_remote = False  # when dev is remote control instance

        self.__device_list = None
        self.__devices_fetched = 0
        self.__playlists_fetched = 0
        self.DEFAULT_VOLUME = 100
        self._playlists = None
        self.regexes = {}
        self.last_played_type = None  # The last uri type that was started
        self.log = LOG

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

    @staticmethod
    def best_result(results):
        """Return best result from a list of result tuples.
        Arguments:
            results (list): list of spotify result tuples
        Returns:
            Best match in list
        """
        if len(results) == 0:
            return SpotifyClient.NOTHING_FOUND
        else:
            results.reverse()
            return sorted(results, key=lambda x: x[0])[-1]

    @staticmethod
    def best_confidence(title, query):
        """Find best match for a title against a query.
        Some titles include ( Remastered 2016 ) and similar info. This method
        will test the raw title and a version that has been parsed to remove
        such information.
        Arguments:
            title: title name from spotify search
            query: query from user
        Returns:
            (float) best condidence
        """
        best = title.lower()
        best_stripped = re.sub(r'(\(.+\)|-.+)$', '', best).strip()
        return max(fuzzy_match(best, query),
                   fuzzy_match(best_stripped, query))

    def load_credentials(self):
        """ Retrieve credentials from the backend and connect to Spotify """
        try:
            creds = OVOSSpotifyCredentials()
            self._spotify = SpotifyConnect(client_credentials_manager=creds)
        except(HTTPError, SpotifyNotAuthorizedError):
            self.log.error('Couldn\'t fetch spotify credentials')

    @property
    def playlists(self):
        """ Playlists, cached for 5 minutes """
        if not self.spotify:
            return []  # No connection, no playlists
        now = time.time()
        if not self._playlists or (now - self.__playlists_fetched > 5 * 60):
            self._playlists = {}
            playlists = self.spotify.current_user_playlists().get('items', [])
            for p in playlists:
                self._playlists[p['name'].lower()] = p
            self.__playlists_fetched = now
        return self._playlists

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

    @property
    def active_device_id(self):
        for d in self.devices:
            if d["is_active"]:
                return d["id"]
        return None

    def device_by_name(self, name):
        """ Get a Spotify devices from the API
        Args:
            name (str): The device name (fuzzy matches)
        Returns:
            (dict) None or the matching device's description
        """
        devices = self.devices
        if devices and len(devices) > 0:
            # Otherwise get a device with the selected name
            devices_by_name = {d['name']: d for d in devices}
            key, confidence = match_one(name, list(devices_by_name.keys()))
            if confidence > 0.5:
                return devices_by_name[key]
        return None

    def get_default_device(self):
        """ Get preferred playback device """
        if self.spotify:
            # When there is an active Spotify device somewhere, use it
            if (self.devices and len(self.devices) > 0 and
                    self.spotify.is_playing()):
                for dev in self.devices:
                    if dev['is_active']:
                        self.log.info('Playing on an active device '
                                      '[{}]'.format(dev['name']))
                        return dev  # Use this device

            # is there a device with ovos in name available?
            for dev in self.devices:
                if "ovos" in dev['name']:
                    self.log.info('Playing on first ovos device '
                                  '[{}]'.format(dev['name']))
                    return dev  # Use this device
            # is there a speaker available?
            for dev in self.devices:
                if dev['type'] == "Speaker":
                    self.log.info('Playing on first spotify speaker '
                                  '[{}]'.format(dev['name']))
                    return dev  # Use this device
            # No playing device found, use the default Spotify device
            dev = self.device_by_name(self.device_name)
            self.is_player_remote = False
            return dev

        return None

    def generic_query(self, phrase, bonus=0):
        """ Check for a generic query, not asking for any special feature.
            This will try to parse the entire phrase in the following order
            - As a user playlist
            - As an album
            - As a track
            - As a public playlist
            Arguments:
                phrase (str): Text to match against
                bonus (float): Any existing match bonus
            Returns: Tuple with confidence and data or NOTHING_FOUND
        """
        self.log.info('Handling "{}" as a genric query...'.format(phrase))
        results = []
        data = {}
        self.log.info('Checking users playlists')
        playlist, conf = self.get_best_user_playlist(phrase)
        if playlist:
            uri = self.playlists[playlist]
            data = {
                'data': uri,
                'name': playlist,
                'type': 'playlist'
            }
        if conf and conf > SpotifyClient.DIRECT_RESPONSE_CONFIDENCE:
            return (conf, data)
        elif conf and conf > SpotifyClient.MATCH_CONFIDENCE:
            results.append((conf, data))

        # Check for artist
        self.log.info('Checking artists')
        conf, data = self.query_artist(phrase, bonus=0)
        if conf and conf > SpotifyClient.DIRECT_RESPONSE_CONFIDENCE:
            return conf, data
        elif conf and conf > SpotifyClient.MATCH_CONFIDENCE:
            results.append((conf, data))

        # Check for track
        self.log.info('Checking tracks')
        conf, data = self.query_song(phrase, bonus=0)
        if conf and conf > SpotifyClient.DIRECT_RESPONSE_CONFIDENCE:
            return conf, data
        elif conf and conf > SpotifyClient.MATCH_CONFIDENCE:
            results.append((conf, data))

        # Check for album
        self.log.info('Checking albums')
        conf, data = self.query_album(phrase, bonus=0)
        if conf and conf > SpotifyClient.DIRECT_RESPONSE_CONFIDENCE:
            return conf, data
        elif conf and conf > SpotifyClient.MATCH_CONFIDENCE:
            results.append((conf, data))

        # Check for public playlist
        self.log.info('Checking public playlists')
        conf, data = self.get_best_public_playlist(phrase)
        if conf and conf > SpotifyClient.DIRECT_RESPONSE_CONFIDENCE:
            return conf, data
        elif conf and conf > SpotifyClient.MATCH_CONFIDENCE:
            results.append((conf, data))

        return self.best_result(results)

    def query_artist(self, artist, bonus=0.0):
        """Try to find an artist.
            Arguments:
                artist (str): Artist to search for
                bonus (float): Any bonus to apply to the confidence
            Returns: Tuple with confidence and data or NOTHING_FOUND
        """
        bonus += 0.1
        data = self.spotify.search(artist, type='artist')
        if data and data['artists']['items']:
            best = data['artists']['items'][0]['name']
            confidence = fuzzy_match(best, artist.lower()) + bonus
            confidence = min(confidence, 1.0)
            return (confidence,
                    {
                        'data': data,
                        'name': None,
                        'type': 'artist'
                    })
        else:
            return SpotifyClient.NOTHING_FOUND

    def query_album(self, album, bonus=0):
        """ Try to find an album.
            Searches Spotify by album and artist if available.
            Arguments:
                album (str): Album to search for
                bonus (float): Any bonus to apply to the confidence
            Returns: Tuple with confidence and data or NOTHING_FOUND
        """
        # TODO localize
        by_word = ' by '
        if len(album.split(by_word)) > 1:
            album, artist = album.split(by_word)
            album_search = '*{}* artist:{}'.format(album, artist)
            bonus += 0.1
        else:
            album_search = album
        data = self.spotify.search(album_search, type='album')
        if data and data['albums']['items']:
            best = data['albums']['items'][0]['name'].lower()
            confidence = self.best_confidence(best, album)
            # Also check with parentheses removed for example
            # "'Hello Nasty ( Deluxe Version/Remastered 2009" as "Hello Nasty")
            confidence = min(confidence + bonus, 1.0)
            self.log.info((album, best, confidence))
            return (confidence,
                    {
                        'data': data,
                        'name': None,
                        'type': 'album'
                    })
        return SpotifyClient.NOTHING_FOUND

    def query_playlist(self, playlist):
        """ Try to find a playlist.
            First searches the users playlists, then tries to find a public
            one.
            Arguments:
                playlist (str): Playlist to search for
            Returns: Tuple with confidence and data or NOTHING_FOUND
        """
        result, conf = self.get_best_user_playlist(playlist)
        if playlist and conf > 0.5:
            uri = self.playlists[result]
            return (conf, {'data': uri,
                           'name': playlist,
                           'type': 'playlist'})
        else:
            return self.get_best_public_playlist(playlist)

    def query_song(self, song, bonus=0):
        """ Try to find a song.
            Searches Spotify for song and artist if provided.
            Arguments:
                song (str): Song to search for
                bonus (float): Any bonus to apply to the confidence
            Returns: Tuple with confidence and data or NOTHING_FOUND
        """
        by_word = ' by '  # TODO lang support
        if len(song.split(by_word)) > 1:
            song, artist = song.split(by_word)
            song_search = '*{}* artist:{}'.format(song, artist)
        else:
            song_search = song

        data = self.spotify.search(song_search, type='track')
        if data and len(data['tracks']['items']) > 0:
            tracks = [(self.best_confidence(d['name'], song), d)
                      for d in data['tracks']['items']]
            tracks.sort(key=lambda x: x[0])
            tracks.reverse()  # Place best matches first
            # Find pretty similar tracks to the best match
            tracks = [t for t in tracks if t[0] > tracks[0][0] - 0.1]
            # Sort remaining tracks by popularity
            tracks.sort(key=lambda x: x[1]['popularity'])
            self.log.debug([(t[0], t[1]['name'], t[1]['artists'][0]['name'])
                            for t in tracks])
            data['tracks']['items'] = [tracks[-1][1]]
            return (tracks[-1][0] + bonus,
                    {'data': data, 'name': None, 'type': 'track'})
        else:
            return SpotifyClient.NOTHING_FOUND

    def get_best_user_playlist(self, playlist):
        """ Get best playlist matching the provided name
        Arguments:
            playlist (str): Playlist name
        Returns: ((str)best match, (float)confidence)
        """
        playlists = self.playlists
        if len(playlists) > 0:
            # Only check if the user has playlists
            key, confidence = match_one(playlist.lower(), playlists)
            if confidence > 0.7:
                return key, confidence
        return SpotifyClient.NOTHING_FOUND

    def get_best_public_playlist(self, playlist):
        data = self.spotify.search(playlist, type='playlist')
        if data and data['playlists']['items']:
            best = data['playlists']['items'][0]
            confidence = fuzzy_match(best['name'].lower(), playlist)
            if confidence > 0.7:
                return (confidence, {'data': best,
                                     'name': best['name'],
                                     'type': 'playlist'})
        return SpotifyClient.NOTHING_FOUND

    def continue_current_playlist(self, dev):
        """ Send the play command to the selected device. """
        self.spotify.play(dev['id'])

    def playback_prerequisits_ok(self):
        """ Check that playback is possible, launch client if neccessary. """
        if self.spotify is None:
            return False
        return True

    @property
    def default_device_id(self):
        if not len(self.devices):
            return None
        if self.active_device_id:
            return self.active_device_id
        for d in self.devices:
            if "ovos" in d["name"]:
                return d["id"]
        dev_id = self.devices[0]["id"]
        return dev_id

    def validate_device_id(self, dev_id):
        if dev_id is None:
            dev_id = self.default_device_id
        else:
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

    def play(self, uris=None, dev_id=None, context_uri=None, repeat=None):
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
            self.log.info(u'spotify_play: {}'.format(dev_id))
            self.spotify.play(dev_id, uris=uris, context_uri=context_uri)
            self.dev_id = dev_id
            if repeat is False:
                self.spotify.repeat("off")
            elif repeat is True:
                self.spotify.repeat("context")
        except spotipy.SpotifyException as e:
            # TODO: Catch other conditions?
            if e.http_status == 403:
                self.log.error('Play command returned 403, play is likely '
                               'already in progress. \n {}'.format(repr(e)))
            else:
                raise SpotifyNotAuthorizedError from e
        except Exception as e:
            self.log.exception(e)
            raise

    def start_playlist_playback(self, uri, name="playlist", dev_id=None):
        dev_id = self.validate_device_id(dev_id)
        dev = self.get_device(dev_id)
        name = name.replace('|', ':')
        if uri:
            self.log.info(u'playing {} using {}'.format(name, dev['name']))
            self.play(dev_id=dev_id, context_uri=uri)
        else:
            self.log.info('No playlist found')
            raise PlaylistNotFoundError

    def search(self, query, search_type):
        """ Search for an album, playlist or artist.
        Arguments:
            query:       search query (album title, artist, etc.)
            search_type: whether to search for an 'album', 'artist',
                         'playlist', 'track', or 'genre'
            TODO: improve results of albums by checking artist
        """
        res = None
        if search_type == 'album' and len(query.split('by')) > 1:
            title, artist = query.split('by')
            result = self.spotify.search(title, type=search_type)
        else:
            result = self.spotify.search(query, type=search_type)

        if search_type == 'album':
            if len(result['albums']['items']) > 0:
                album = result['albums']['items'][0]
                self.log.info(album)
                res = album
        elif search_type == 'artist':
            self.log.info(result['artists'])
            if len(result['artists']['items']) > 0:
                artist = result['artists']['items'][0]
                self.log.info(artist)
                res = artist
        elif search_type == 'genre':
            self.log.debug("TODO! Genre")
        else:
            self.log.error('Search type {} not supported'.format(search_type))
            return

        return res

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

