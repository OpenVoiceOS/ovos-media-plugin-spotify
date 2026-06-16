"""Import, interface and entry-point wiring tests for the Spotify OCP plugin.

These tests deliberately avoid instantiating the plugin or its SpotifyClient,
which would require live Spotify OAuth credentials and network access. They
validate the parts of the public surface that must stay stable for OPM to
discover and load the plugin.
"""
from importlib.metadata import entry_points

from ovos_plugin_manager.templates.media import AudioPlayerBackend


def test_class_is_exported_from_package_root():
    import ovos_media_plugin_spotify as pkg

    assert hasattr(pkg, "SpotifyOCPAudioService")


def test_plugin_implements_audio_player_backend():
    from ovos_media_plugin_spotify import SpotifyOCPAudioService

    assert issubclass(SpotifyOCPAudioService, AudioPlayerBackend)


def test_opm_entry_point_loads_to_the_plugin_class():
    from ovos_media_plugin_spotify import SpotifyOCPAudioService

    eps = entry_points(group="opm.media.audio")
    matches = [ep for ep in eps if ep.name == "ovos-media-audio-plugin-spotify"]
    assert matches, "opm.media.audio entry point not registered"
    assert matches[0].load() is SpotifyOCPAudioService


def test_legacy_audioservice_entry_point_module_imports():
    eps = entry_points(group="mycroft.plugin.audioservice")
    matches = [ep for ep in eps if ep.name == "ovos_spotify"]
    assert matches, "mycroft.plugin.audioservice entry point not registered"
    module = matches[0].load()
    assert hasattr(module, "SpotifyAudioService")
