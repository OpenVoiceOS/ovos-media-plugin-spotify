from pprint import pprint

from ovos_config.config import MycroftUserConfig

from ovos_media_plugin_spotify.spotify_client import SpotifyClient


def main():
    print(
        """This script will auto configure ALL spotify devices under your mycroft.conf
        
        SPOTIFY PREMIUM is required!
        
        If you have not yet authenticated your spotify account, run 'ovos-spotify-oauth' first!
        """)
    cfg = MycroftUserConfig()
    spotify = SpotifyClient()
    for d in spotify.devices:
        print(f"Found device: {d['name']}")

        if "Audio" not in cfg:
            cfg["Audio"] = {}
        if "backends" not in cfg["Audio"]:
            cfg["Audio"]["backends"] = {}
        if "media" not in cfg:
            cfg["media"] = {}
        if "audio_players" not in cfg["media"]:
            cfg["media"]["audio_players"] = {}

        cfg["Audio"]["backends"]["spotify-" + d['name']] = {
            "type": "ovos_spotify",
            "identifier": d['name'],
            "active": True
        }
        cfg["media"]["audio_players"]["spotify-" + d['name']] = {
            "module": "ovos-media-audio-plugin-spotify",
            "identifier": d['name'],
            "aliases": [d['name']],
            "active": True
        }
    cfg.store()

    print("\nmycroft.conf updated!")
    print("\n# Legacy Audio Service:")
    pprint(cfg["Audio"])
    print("\n# ovos-media Service:")
    pprint(cfg["media"])


if __name__ == "__main__":
    main()
