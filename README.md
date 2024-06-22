# ovos-media-plugin-spotify

spotify plugin for [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) and [ovos-media](https://github.com/OpenVoiceOS/ovos-media)

allows OVOS to initiate playback on spotify 

> NOTE: [the companion skill](https://github.com/OpenVoiceOS/skill-ovos-spotify) is needed to integrate with voice search

## Install

`pip install ovos-media-plugin-spotify`

## Oauth

Currently Oauth needs to be performed manually

after installing the plugin run `ovos-spotify-oauth` on the command line and follow the instructions

```
$ ovos-spotify-oauth
This script creates the token information needed for running spotify
        with a set of personal developer credentials.

        It requires the user to go to developer.spotify.com and set up a
        developer account, create an "Application" and make sure to whitelist
        "https://localhost:8888".

        After you have done that enter the information when prompted and follow
        the instructions given.
        
YOUR CLIENT ID: xxxxx
YOUR CLIENT SECRET: xxxxx
Go to the following URL: https://accounts.spotify.com/authorize?client_id=xxx&response_type=code&redirect_uri=https%3A%2F%2Flocalhost%3A8888&scope=user-library-read+streaming+playlist-read-private+user-top-read+user-read-playback-state
Enter the URL you were redirected to: https://localhost:8888/?code=.....
ocp_spotify oauth token saved
```

## Configuration

edit your mycroft.conf with any spotify players you want to expose

> NOTE: If you want to make the OVOS device itself a spotify player, we recommend [spotifyd](https://github.com/Spotifyd/spotifyd).

The easiest way is to use the provided `ovos-spotify-autoconfigure` command

```bash
$ ovos-spotify-autoconfigure
This script will auto configure ALL spotify devices under your mycroft.conf
        
        SPOTIFY PREMIUM is required!
        
        If you have not yet authenticated your spotify account, run 'ovos-spotify-oauth' first!
        
Found device: OpenVoiceOS-TV

mycroft.conf updated!

# Legacy Audio Service:
{'backends': {'spotify-OpenVoiceOS-TV': {'active': True,
                                         'identifier': 'OpenVoiceOS-TV',
                                         'type': 'ovos_spotify'}}}

# ovos-media Service:
{'audio_players': {'spotify-OpenVoiceOS-TV': {'active': True,
                                              'aliases': ['OpenVoiceOS-TV'],
                                              'identifier': 'OpenVoiceOS-TV',
                                              'module': 'ovos-media-audio-plugin-spotify'}}}
```

### ovos-audio

```javascript
{
  "Audio": {
    "backends": {
      "spotify": {
        "type": "ovos_spotify",
        "identifier": "device_name_in_spotify",
        "active": true
      }
    }
  }
}
```

### ovos-media

> **WARNING**: `ovos-media' has not yet been released, WIP

```javascript
{
 "media": {
    "audio_players": {
        "desk_speaker": {
            "module": "ovos-media-audio-plugin-spotify",
            
            // this needs to be the name of the device on spotify!
            "identifier": "Mark2",

            // users may request specific handlers in the utterance
            // using these aliases
            "aliases": ["office spotify", "office", "desk", "workstation"],

            // deactivate a plugin by setting to false
            "active": true
        }
    }
}
```

## Python usage

if you don't want to use [the companion skill](https://github.com/OpenVoiceOS/skill-ovos-spotify), you can also write your own integrations

```python
s = SpotifyClient()
# pprint(s.query_album("hail and kill by manowar")[1])

from ovos_utils.skills.audioservice import ClassicAudioServiceInterface
from ovos_utils.messagebus import FakeBus

bus = FakeBus()
audio = ClassicAudioServiceInterface(bus)

audio.play("spotify:playlist:37i9dQZF1DX08jcQJXDnEQ")
audio.play(["spotify:track:5P2Ghhv0wFYThHfDQaS0g5",
            "spotify:playlist:37i9dQZF1DX08jcQJXDnEQ"])
time.sleep(5)
audio.pause()
time.sleep(5)

audio.resume()
time.sleep(5)

audio.next()
time.sleep(5)

audio.prev()
time.sleep(5)

print(audio.track_info())
```
