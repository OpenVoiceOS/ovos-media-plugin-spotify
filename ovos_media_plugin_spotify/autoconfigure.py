from pprint import pprint

from ovos_config.config import MycroftUserConfig

from ovos_media_plugin_spotify.spotify_client import SpotifyClient


def main():
    print(
        """This script will auto configure spotify devices under your mycroft.conf
        
        SPOTIFY PREMIUM is required!
        
        If you have not yet authenticated your spotify account, run 'ovos-spotify-oauth' first!
        """)
    cfg = MycroftUserConfig()
    spotify = SpotifyClient()
    devices = [d['name'] for d in spotify.devices]
    if not devices:
        print("ERROR: no spotify devices found in this account")
        exit(1)

    print(f"Found devices: {devices}")
    if len(devices) == 1:
        default = 0
    else:
        for idx, d in enumerate(devices):
            print(f"{idx} - {d}")
        default = int(input("select default spotify device:"))

    for idx, d in enumerate(devices):
        if "media" not in cfg:
            cfg["media"] = {}
        if "audio_players" not in cfg["media"]:
            cfg["media"]["audio_players"] = {}

        if idx == default:
            if "Audio" not in cfg:
                cfg["Audio"] = {}
            if "backends" not in cfg["Audio"]:
                cfg["Audio"]["backends"] = {}
            cfg["Audio"]["backends"]["spotify-" + d] = {
                "type": "ovos_spotify",
                "identifier": d,
                "active": True
            }

        cfg["media"]["audio_players"]["spotify-" + d] = {
            "module": "ovos-media-audio-plugin-spotify",
            "identifier": d,
            "aliases": [d.replace("-", " ")],
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
