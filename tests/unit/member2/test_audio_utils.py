import numpy as np
import pytest

from nexa.audio import chunks, mixer, vad, wav_utils

SR = 16000


def tone(seconds: float, freq: float = 440.0, amp: float = 8000.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def test_wav_roundtrip(tmp_path):
    x = tone(0.5)
    p = tmp_path / "a.wav"
    wav_utils.write_wav(p, x, SR)
    y, rate = wav_utils.read_wav(p)
    assert rate == SR and np.array_equal(x, y)
    assert wav_utils.wav_duration_ms(p) == 500


def test_stereo_to_mono_averages():
    stereo = np.array([1000, 3000, -2000, 2000], dtype=np.int16)  # 2 frames, 2 channels
    assert wav_utils.to_mono(stereo, 2).tolist() == [2000, 0]


def test_resample_length_and_pitch_preserved():
    x = tone(1.0, freq=440, sr=48000)
    y = wav_utils.resample(x, 48000, SR)
    assert len(y) == SR
    # dominant frequency stays 440 Hz
    freqs = np.fft.rfftfreq(len(y), 1 / SR)
    assert abs(freqs[np.argmax(np.abs(np.fft.rfft(y)))] - 440) < 5


def test_resample_noop_when_same_rate():
    x = tone(0.1)
    assert np.array_equal(wav_utils.resample(x, SR, SR), x)


def test_read_wav_rejects_non_16bit(tmp_path):
    import wave

    p = tmp_path / "bad.wav"
    with wave.open(str(p), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(SR)
        wf.writeframes(b"\x80" * 100)
    with pytest.raises(ValueError):
        wav_utils.read_wav(p)


def test_mix_pads_shorter_and_never_clips():
    a = np.full(100, 30000, dtype=np.int16)
    b = np.full(50, 30000, dtype=np.int16)
    m = mixer.mix_mono(a, b)
    assert len(m) == 100
    assert int(np.max(np.abs(m))) <= 32767
    assert m[0] > m[99]  # overlap region is scaled together, tail (a only) is not louder


def test_mix_wav_files(tmp_path):
    wav_utils.write_wav(tmp_path / "a.wav", tone(1.0, 300), SR)
    wav_utils.write_wav(tmp_path / "b.wav", tone(0.5, 900), SR)
    ms = mixer.mix_wav_files(str(tmp_path / "a.wav"), str(tmp_path / "b.wav"), str(tmp_path / "m.wav"))
    assert ms == 1000


def test_level_db_and_silence():
    assert vad.level_db(np.zeros(1000, dtype=np.int16)) == -90.0
    assert vad.is_silent(np.zeros(1000, dtype=np.int16))
    assert not vad.is_silent(tone(0.1))
    assert vad.peak_db(tone(0.1, amp=16384)) == pytest.approx(-6.0, abs=0.1)


def test_speech_regions_finds_short_burst_and_keeps_padding():
    rng = np.random.default_rng(0)
    noise = (rng.normal(0, 30, SR * 3)).astype(np.int16)
    audio = noise.copy()
    audio[SR : SR + 3200] = tone(0.2, amp=9000)  # one 200 ms "word" at t=1.0 s
    regions = vad.speech_regions(audio, SR)
    assert len(regions) == 1
    start, end = regions[0]
    assert start <= 1000 and end >= 1200  # padded, word fully inside


def test_speech_regions_empty_for_pure_silence_or_tiny_input():
    assert vad.speech_regions(np.zeros(SR, dtype=np.int16), SR) == []
    assert vad.speech_regions(np.zeros(10, dtype=np.int16), SR) == []


def test_chunk_writer_hard_split_is_sample_exact(tmp_path):
    w = chunks.ChunkWriter(tmp_path, "mic", SR, target_seconds=1.0, max_seconds=1.0)
    w.write(tone(2.5))
    paths = w.close()
    assert [wav_utils.wav_duration_ms(p) for p in paths] == [1000, 1000, 500]


def test_chunk_writer_cuts_at_silence_after_target(tmp_path):
    w = chunks.ChunkWriter(tmp_path, "mic", SR, target_seconds=1.0, max_seconds=5.0)
    w.write(tone(1.2))  # past target but loud -> keep going
    w.write(np.zeros(1600, dtype=np.int16))  # silent block -> cut
    w.write(tone(0.3))
    paths = w.close()
    assert len(paths) == 2
    assert wav_utils.wav_duration_ms(paths[0]) == 1300


def test_concat_and_find_chunks(tmp_path):
    w = chunks.ChunkWriter(tmp_path, "loop", SR, target_seconds=1.0, max_seconds=1.0)
    w.write(tone(2.0))
    paths = w.close()
    assert chunks.find_chunks(tmp_path, "loop") == paths
    assert chunks.concat_wavs(paths, tmp_path / "all.wav") == 2 * SR
