#!/usr/bin/env python3
import os
from setuptools import setup

BASEDIR = os.path.abspath(os.path.dirname(__file__))


def get_version():
    """ Find the version of the package"""
    version_file = os.path.join(BASEDIR, 'ovos_media_plugin_spotify', 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version


def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join('..', path, filename))
    return paths


def required(requirements_file):
    """ Read requirements file and remove comments and empty lines. """
    with open(os.path.join(BASEDIR, requirements_file), 'r') as f:
        requirements = f.read().splitlines()
        if 'MYCROFT_LOOSE_REQUIREMENTS' in os.environ:
            print('USING LOOSE REQUIREMENTS!')
            requirements = [r.replace('==', '>=').replace('~=', '>=') for r in requirements]
        return [pkg for pkg in requirements
                if pkg.strip() and not pkg.startswith("#")]


PLUGIN_ENTRY_POINT = 'ovos-media-audio-plugin-spotify=ovos_media_plugin_spotify:SpotifyOCPAudioService'
OLD_PLUGIN_ENTRY_POINT = 'ovos_spotify=ovos_media_plugin_spotify.audio'


with open(os.path.join(BASEDIR, "README.md"), "r") as f:
    long_description = f.read()

setup(
    name='ovos-media-plugin-spotify',
    version=get_version(),
    description='spotify plugin for ovos',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/OpenVoiceOS/ovos-media-plugin-spotify',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    packages=['ovos_media_plugin_spotify'],
    install_requires=required("requirements/requirements.txt"),
    package_data={'': package_files('ovos_media_plugin_spotify')},
    keywords='ovos audio video OCP plugin',
    entry_points={'opm.media.audio': PLUGIN_ENTRY_POINT,
                  'mycroft.plugin.audioservice': OLD_PLUGIN_ENTRY_POINT,
                  'console_scripts': [
                      'ovos-spotify-oauth=ovos_media_plugin_spotify.auth:main',
                      'ovos-spotify-autoconfigure=ovos_media_plugin_spotify.autoconfigure:main'
                  ]
                  }
)
