import sys
from array import array
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from voice_control_pc.audio import record_microphone_to_wav
from voice_control_pc.models import AudioSettings


def fake_audio(monkeypatch, chunks=None, open_error=None):
    stream = Mock()
    stream.read.side_effect = chunks or [array("h", [1200] * 1024).tobytes()] * 16
    device = Mock()
    device.get_sample_size.return_value = 2
    device.open.side_effect = open_error
    device.open.return_value = stream
    module = SimpleNamespace(PyAudio=lambda: device, paInt16=1, paInt24=2, paInt32=3, paFloat32=4)
    monkeypatch.setitem(sys.modules, "pyaudio", module)
    return device, stream


def test_audio_cleanup_on_open_failure(tmp_path, monkeypatch):
    device, _ = fake_audio(monkeypatch, open_error=OSError("no microphone"))
    with pytest.raises(OSError):
        record_microphone_to_wav(tmp_path / "a.wav", AudioSettings())
    device.terminate.assert_called_once()


def test_silence_is_not_transcribed(tmp_path, monkeypatch):
    device, stream = fake_audio(monkeypatch, chunks=[bytes(2048)] * 16)
    with pytest.raises(RuntimeError, match="Речь не обнаружена"):
        record_microphone_to_wav(tmp_path / "a.wav", AudioSettings(max_seconds=1))
    stream.close.assert_called_once()
    device.terminate.assert_called_once()
    assert not (tmp_path / "a.wav").exists()


def test_recording_saves_valid_wav_and_closes_resources(tmp_path, monkeypatch):
    import wave

    device, stream = fake_audio(monkeypatch)
    path = record_microphone_to_wav(tmp_path / "a.wav", AudioSettings(max_seconds=1))
    with wave.open(str(path)) as audio:
        assert audio.getframerate() == 16000
        assert audio.getnframes() > 0
    stream.stop_stream.assert_called_once()
    stream.close.assert_called_once()
    device.terminate.assert_called_once()
