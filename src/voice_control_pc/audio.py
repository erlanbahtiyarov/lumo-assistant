"""Bounded microphone recording with cancellation, silence detection and reliable cleanup."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path
from threading import Event

from voice_control_pc.models import AudioSettings


def _pyaudio():
    try:
        import pyaudio
    except ImportError as error:
        raise RuntimeError("Микрофон недоступен: установите Lumo с компонентом [voice]") from error
    return pyaudio


def list_input_devices() -> list[dict[str, str | int]]:
    audio = _pyaudio().PyAudio()
    try:
        result = []
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) > 0:
                result.append(
                    {
                        "index": index,
                        "name": str(info.get("name", index)),
                        "channels": int(info["maxInputChannels"]),
                    }
                )
        return result
    finally:
        audio.terminate()


def record_microphone_to_wav(
    output_path: Path,
    settings: AudioSettings,
    duration_seconds: int | None = None,
    device_index: int | None = None,
    stop_event: Event | None = None,
) -> Path:
    duration = duration_seconds if duration_seconds is not None else settings.max_seconds
    if not 0 < duration <= 30:
        raise ValueError("Длительность записи должна быть от 1 до 30 секунд")
    module = _pyaudio()
    sample_format = _resolve_sample_format(module, settings.sample_format)
    audio = module.PyAudio()
    stream = None
    frames = []
    voiced = False
    silent_ms = 0.0
    try:
        sample_width = audio.get_sample_size(sample_format)
        stream = audio.open(
            format=sample_format,
            channels=settings.channels,
            rate=settings.sample_rate,
            input=True,
            frames_per_buffer=settings.chunk_size,
            input_device_index=device_index if device_index is not None else settings.device_index,
        )
        for _ in range(math.ceil(settings.sample_rate * duration / settings.chunk_size)):
            if stop_event is not None and stop_event.is_set():
                break
            chunk = stream.read(settings.chunk_size, exception_on_overflow=False)
            frames.append(chunk)
            if settings.sample_format == "int16":
                samples = array("h", chunk)
                rms = math.sqrt(sum(v * v for v in samples) / max(len(samples), 1))
                if rms > settings.silence_threshold:
                    voiced, silent_ms = True, 0
                elif voiced:
                    silent_ms += 1000 * settings.chunk_size / settings.sample_rate
                    if silent_ms >= settings.silence_timeout_ms:
                        break
    finally:
        try:
            if stream is not None:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
        finally:
            audio.terminate()
    if not frames:
        raise RuntimeError("Запись отменена")
    if settings.sample_format == "int16" and not voiced:
        raise RuntimeError("Речь не обнаружена. Проверьте микрофон и порог тишины.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(settings.channels)
        output.setsampwidth(sample_width)
        output.setframerate(settings.sample_rate)
        output.writeframes(b"".join(frames))
    return output_path


def _resolve_sample_format(module, name: str):
    values = {
        "int16": module.paInt16,
        "int24": module.paInt24,
        "int32": module.paInt32,
        "float32": module.paFloat32,
    }
    if name not in values:
        raise ValueError(f"Неизвестный формат аудио: {name}")
    return values[name]
