

# WIP WIP WIP WIP WIP it's spotify for the OpenVoiceOS ecosystem


# Setup


wait for this plugin and companion skill to be ready

```python

# TODO companion skill
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