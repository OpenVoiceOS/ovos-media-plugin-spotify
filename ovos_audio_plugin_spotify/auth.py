# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from os import mkdir
from os.path import exists, join

from ovos_backend_client.database import OAuthTokenDatabase, OAuthApplicationDatabase
from ovos_utils.xdg_utils import xdg_config_home
from spotipy import SpotifyOAuth

AUTH_DIR = os.environ.get('SPOTIFY_SKILL_CREDS_DIR', f"{xdg_config_home()}/spotipy")
SCOPE = ('user-library-read streaming playlist-read-private user-top-read '
         'user-read-playback-state')


def ensure_auth_dir_exists():
    if not exists(AUTH_DIR):
        mkdir(AUTH_DIR)


if __name__ == '__main__':
    print(
        """This script creates the token information needed for running spotify
        with a set of personal developer credentials.

        It requires the user to go to developer.spotify.com and set up a
        developer account, create an "Application" and make sure to whitelist
        "https://localhost:8888".

        After you have done that enter the information when prompted and follow
        the instructions given.
        """)

    CLIENT_ID = input('YOUR CLIENT ID: ')
    CLIENT_SECRET = input('YOUR CLIENT SECRET: ')
    REDIRECT_URI = 'https://localhost:8888'
    TOKEN_ID = "ocp_spotify"
    PORT = 36536  # Oauth phal plugin

    os.makedirs(AUTH_DIR, exist_ok=True)
    am = SpotifyOAuth(scope=SCOPE, client_id=CLIENT_ID,
                      client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI,
                      cache_path=join(AUTH_DIR, 'token'),
                      open_browser=False)

    with OAuthApplicationDatabase() as db:
        db.add_application(oauth_service=TOKEN_ID,
                           client_id=CLIENT_ID,
                           client_secret=CLIENT_SECRET,
                           auth_endpoint="https://accounts.spotify.com/authorize?",
                           token_endpoint="https://accounts.spotify.com/api/token",
                           refresh_endpoint="https://accounts.spotify.com/api/token",
                           callback_endpoint=f"http://0.0.0.0:{PORT}/auth/callback/{TOKEN_ID}",
                           scope=SCOPE[0])

    token_info = am.validate_token(am.cache_handler.get_cached_token())
    if not token_info or True:
        code = am.get_auth_response()
        token = am.get_access_token(code, as_dict=False)
        token_info = am.validate_token(am.cache_handler.get_cached_token())

    with OAuthTokenDatabase() as db:
        db.add_token(TOKEN_ID, token_info)

    print(TOKEN_ID, "oauth token saved")
