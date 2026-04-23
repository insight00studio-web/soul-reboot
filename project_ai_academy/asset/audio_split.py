"""asset/audio_split.py - WAV を無音区間で分割するユーティリティ。

マルチスピーカー TTS で1コール出力された WAV を、各話者ターンごとに
切り出すために使用する。期待数と一致しない場合は None を返し、
呼び出し側はフォールバック（行ごと個別生成）に切り替える。
"""

import wave

import numpy as np


def _read_pcm_mono(wav_path: str) -> tuple[np.ndarray, int, int]:
    """WAV から PCM サンプル（mono float32, -1.0〜1.0）と framerate, sampwidth を取得。"""
    with wave.open(wav_path, "rb") as wf:
        framerate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        nchannels = wf.getnchannels()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Unsupported sampwidth: {sampwidth}")

    if nchannels > 1:
        data = data.reshape(-1, nchannels).mean(axis=1)

    return data, framerate, sampwidth


def _detect_silence_regions(
    samples: np.ndarray,
    framerate: int,
    threshold_db: float,
    min_silence_sec: float,
) -> list[tuple[int, int]]:
    """各サンプル位置の RMS から無音区間 [(start_sample, end_sample), ...] を返す。"""
    window_size = max(1, int(framerate * 0.02))  # 20ms 窓
    n_windows = len(samples) // window_size
    if n_windows == 0:
        return []

    trimmed = samples[: n_windows * window_size].reshape(n_windows, window_size)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms + 1e-12)
    is_silent = db < threshold_db

    min_silent_windows = max(1, int(min_silence_sec / 0.02))

    regions: list[tuple[int, int]] = []
    in_silence = False
    silence_start = 0
    for i, silent in enumerate(is_silent):
        if silent and not in_silence:
            in_silence = True
            silence_start = i
        elif not silent and in_silence:
            in_silence = False
            length = i - silence_start
            if length >= min_silent_windows:
                regions.append((silence_start * window_size, i * window_size))
    if in_silence:
        length = n_windows - silence_start
        if length >= min_silent_windows:
            regions.append((silence_start * window_size, n_windows * window_size))

    return regions


def split_wav_by_silence(
    wav_path: str,
    expected_count: int,
    min_silence_sec: float = 0.4,
    threshold_db: float = -40.0,
) -> list[tuple[float, float]] | None:
    """WAV を無音中点で分割し、 [(start_sec, end_sec), ...] を返す。

    検出セグメント数が expected_count と一致した場合のみ返す。
    一致しない場合は None（呼び出し側でフォールバック）。
    """
    if expected_count < 1:
        return None

    samples, framerate, _ = _read_pcm_mono(wav_path)
    total_sec = len(samples) / framerate

    # 先頭・末尾の無音はトリム対象として扱わず、内部の無音だけ分割点候補にする
    regions = _detect_silence_regions(samples, framerate, threshold_db, min_silence_sec)
    internal_regions = [
        (s, e) for (s, e) in regions if s > 0 and e < len(samples)
    ]

    needed_splits = expected_count - 1
    print(f"    [SPLIT] detected {len(internal_regions)} internal silences, need {needed_splits}")

    if len(internal_regions) < needed_splits:
        # 必要数に足りない → 諦めてフォールバック
        return None

    # 必要数より多く検出された場合は、長い無音ほど話者交代の境界らしいので
    # 上位 needed_splits 個を採用（位置順に並べ直す）
    if len(internal_regions) > needed_splits:
        sorted_by_length = sorted(
            internal_regions, key=lambda r: r[1] - r[0], reverse=True
        )
        chosen = sorted(sorted_by_length[:needed_splits], key=lambda r: r[0])
    else:
        chosen = internal_regions

    # 各無音区間の中点を分割点に
    split_points_sec = [
        ((s + e) / 2.0) / framerate for (s, e) in chosen
    ]

    boundaries = [0.0] + split_points_sec + [total_sec]
    return [(boundaries[i], boundaries[i + 1]) for i in range(expected_count)]


def write_wav_segment(
    src_wav_path: str,
    dst_wav_path: str,
    start_sec: float,
    end_sec: float,
) -> None:
    """src_wav_path の [start_sec, end_sec) を dst_wav_path に書き出す。"""
    with wave.open(src_wav_path, "rb") as wf:
        framerate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        nchannels = wf.getnchannels()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    bytes_per_frame = sampwidth * nchannels
    start_byte = int(start_sec * framerate) * bytes_per_frame
    end_byte = int(end_sec * framerate) * bytes_per_frame
    segment = raw[start_byte:end_byte]

    with wave.open(dst_wav_path, "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(segment)
