# Member 2 - manual test checklist (Windows, ROG)

The hardware layer (`audio/capture.py`, `devices.py`, `microphone.py`, `loopback.py`) was written without access
to a Windows audio device. Nothing below has been run yet.

## Setup
```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements\base.txt -r requirements\dev.txt -r requirements\audio_windows.txt
```

## Checks

- [ ] **List devices**
  `python -c "from nexa.audio.devices import PyAudioDeviceService as S; s=S(); print(s.list_inputs()); print(s.list_loopback_outputs())"`
  (run with `set PYTHONPATH=src`). Expect your mic(s) and at least one loopback device.
- [ ] **Mic only, 10 s.** Speak, stop, open `recording.wav` - it is mono 16 kHz and audible.
- [ ] **Computer audio only, 10 s** with a YouTube video playing. Expect the video's audio.
- [ ] **Loopback while nothing plays.** Start `COMPUTER`, stay silent for 20 s, then play audio for 5 s.
      Expect ~25 s total (WASAPI sends no data during silence; the recorder should pad with zeros) and the stop must not hang.
- [ ] **Both, 60 s** - talk while a video plays. Both voices audible, no clipping/distortion, video and speech in sync.
- [ ] **Device with a different sample rate** (e.g. Bluetooth headset at 44.1 kHz / 24 kHz): audio plays at normal speed and pitch.
- [ ] **Pause / resume** - paused span is missing, no crash.
- [ ] **Unplug the mic mid-recording.** `recorder.warnings` reports the failure; earlier audio is still returned.
- [ ] **Kill the process mid-recording** (Task Manager), then `recover_recording(<workdir>)` returns everything up to the last chunk.
- [ ] **Long run, 60-90 min** with both sources: no memory growth, chunk files ~60 s each, `recording.wav` duration matches wall-clock.
- [ ] **Dead-mic check**: `measure_source` on a muted mic reports `looks_dead`.

Record anything that fails as an issue with the device name and Windows version; the likely trouble spots are
`PyAudioCapture._resolve_device` (loopback device selection) and multi-channel handling in `to_mono`.
