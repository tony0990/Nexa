import time

import numpy as np
import pytest

from nexa.audio import recorder as rec
from nexa.audio.capture import AudioBackendError
from nexa.audio.wav_utils import read_wav, wav_duration_ms, write_wav
from nexa.contracts.audio import AudioSource, SourceConfig

from .test_audio_utils import tone


class FakeCapture:
    """Delivers a 100 ms block every 100 ms of real time; `starved=True` delivers nothing
    (like WASAPI loopback while the system is silent)."""

    def __init__(self, rate: int = 16000, amp: float = 8000.0, freq: float = 440.0, starved: bool = False):
        self.sample_rate = rate
        self._block = tone(0.1, freq=freq, amp=amp, sr=rate)
        self._starved = starved
        self._next = None
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        self._next = time.monotonic()

    def read_block(self, timeout: float):
        if self._starved:
            time.sleep(timeout)
            return None
        self._next += 0.1
        time.sleep(max(0.0, self._next - time.monotonic()))
        return self._block

    def stop(self):
        self.stopped = True


def factory_for(**captures):
    made = {}

    def factory(kind, index):
        made[kind] = captures[kind]
        return captures[kind]

    factory.made = made
    return factory


def run_for(recorder, config, seconds):
    recorder.start(config)
    time.sleep(seconds)
    return recorder.stop()


def test_microphone_only_records_wall_clock_duration(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture()))
    audio = run_for(r, SourceConfig(AudioSource.MICROPHONE), 1.2)
    assert abs(audio.duration_ms - 1200) < 400
    assert audio.sample_rate == 16000
    samples, rate = read_wav(audio.path)
    assert rate == 16000 and np.max(np.abs(samples)) > 1000  # real signal, not silence
    assert len(audio.chunk_paths) >= 1


def test_start_accepts_kickoff_source_string_and_reports_source(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(loop=FakeCapture()))
    audio = run_for(r, "COMPUTER", 0.5)
    assert audio.source == "COMPUTER"


def test_both_mode_reports_what_was_actually_captured(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture(), loop=FakeCapture()))
    assert run_for(r, SourceConfig(AudioSource.BOTH), 0.5).source == "BOTH"


def test_48k_source_is_resampled_to_16k(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture(rate=48000)))
    audio = run_for(r, SourceConfig(AudioSource.MICROPHONE), 1.0)
    assert abs(audio.duration_ms - 1000) < 400
    assert read_wav(audio.path)[1] == 16000


def test_both_mode_pads_starved_loopback_and_mixes(tmp_path):
    mic = FakeCapture(freq=300)
    loop = FakeCapture(starved=True)
    r = rec.Recorder(tmp_path, factory_for(mic=mic, loop=loop), chunk_seconds=1.0)
    audio = run_for(r, SourceConfig(AudioSource.BOTH), 2.5)
    # loopback delivered nothing, yet lengths match the mic (wall-clock padding)
    assert abs(audio.duration_ms - 2500) < 500
    assert len(audio.chunk_paths) >= 2  # fixed 1 s chunks in BOTH mode
    samples, _ = read_wav(audio.path)
    assert np.max(np.abs(samples)) > 1000
    assert mic.stopped and loop.stopped


def test_both_mode_sums_signal_from_both_sources(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture(freq=300), loop=FakeCapture(freq=900)), chunk_seconds=5.0)
    audio = run_for(r, SourceConfig(AudioSource.BOTH), 1.0)
    samples, rate = read_wav(audio.path)
    spectrum = np.abs(np.fft.rfft(samples[: rate]))
    freqs = np.fft.rfftfreq(rate, 1 / rate)
    strong = freqs[spectrum > 0.3 * spectrum.max()]
    assert any(abs(strong - 300) < 15) and any(abs(strong - 900) < 15)


def test_pause_drops_audio(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture()))
    r.start(SourceConfig(AudioSource.MICROPHONE))
    time.sleep(0.6)
    r.pause()
    time.sleep(0.8)
    r.resume()
    time.sleep(0.6)
    audio = r.stop()
    assert abs(audio.duration_ms - 1200) < 450  # not ~2000


def test_start_twice_and_stop_without_start(tmp_path):
    r = rec.Recorder(tmp_path, factory_for(mic=FakeCapture()))
    with pytest.raises(RuntimeError):
        r.stop()
    r.start(SourceConfig(AudioSource.MICROPHONE))
    with pytest.raises(RuntimeError):
        r.start(SourceConfig(AudioSource.MICROPHONE))
    r.stop()


def test_bad_device_fails_on_start_and_cleans_up_other_source(tmp_path):
    mic = FakeCapture()

    class Broken(FakeCapture):
        def start(self):
            raise AudioBackendError("no loopback device")

    r = rec.Recorder(tmp_path, factory_for(mic=mic, loop=Broken()))
    with pytest.raises(AudioBackendError):
        r.start(SourceConfig(AudioSource.BOTH))
    assert mic.stopped and not r.is_recording


def test_recover_recording_salvages_unclosed_last_chunk(tmp_path):
    workdir = tmp_path / "crashed"
    good = workdir / "mic" / "mic_0001.wav"
    unclosed = workdir / "mic" / "mic_0002.wav"
    write_wav(good, tone(1.0))
    write_wav(unclosed, tone(0.5))
    data = bytearray(unclosed.read_bytes())
    data[4:8] = b"\x00\x00\x00\x00"  # RIFF size and data size never patched -> as after a crash
    data[40:44] = b"\x00\x00\x00\x00"
    unclosed.write_bytes(bytes(data))

    audio = rec.recover_recording(workdir)
    assert abs(audio.duration_ms - 1500) < 5
    assert len(audio.chunk_paths) == 2


def test_recover_recording_with_nothing_raises(tmp_path):
    with pytest.raises(AudioBackendError):
        rec.recover_recording(tmp_path / "empty")


def test_measure_source_reports_levels_and_dead_source():
    live = rec.measure_source(FakeCapture(), seconds=0.4)
    assert live.rms_db > -30 and not live.looks_dead
    dead = rec.measure_source(FakeCapture(starved=True), seconds=0.3)
    assert dead.looks_dead
