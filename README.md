# ovos-media-plugin-spotify

spotify plugin for [ovos-media](https://github.com/OpenVoiceOS/ovos-media)

allows OVOS to initiate playback on spotify 

NOTE: [the companion skill](https://github.com/OpenVoiceOS/skill-ovos-spotify) is needed to integrate with voice search

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

```javascript
{
 "media": {
    "audio_players": {
        "kitchen_chromecast": {
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
