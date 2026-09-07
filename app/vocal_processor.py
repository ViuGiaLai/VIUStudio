import os
import warnings

import numpy as np
import soundfile as sf
import librosa
import onnxruntime as ort
from scipy.signal.windows import hann as periodic_hann

from runtime_paths import bin_path

warnings.filterwarnings("ignore", message="NOLA condition failed")

_MODEL_PATH = None
_ONNX_SESSION = None

DIM_F = 3072
DIM_T = 256
N_FFT = DIM_F * 2
HOP = 1024
SR = 44100
L = 11
HALF_DIM_C = 2


def _model_path():
    global _MODEL_PATH
    if _MODEL_PATH is None:
        _MODEL_PATH = os.path.join(bin_path(), "UVR-MDX-NET-Inst_HQ_3.onnx")
    return _MODEL_PATH


def _get_session():
    global _ONNX_SESSION
    if _ONNX_SESSION is None:
        path = _model_path()
        if not os.path.exists(path):
            raise FileNotFoundError(f"ONNX model not found: {path}")
        _ONNX_SESSION = ort.InferenceSession(
            path,
            providers=["CPUExecutionProvider"],
        )
    return _ONNX_SESSION


class _STFT:
    def __init__(self):
        self.dim_c = 4
        self.dim_f = DIM_F
        self.dim_t = DIM_T
        self.n_fft = N_FFT
        self.hop = HOP
        self.n_bins = N_FFT // 2 + 1
        self.chunk_size = HOP * (DIM_T - 1)
        window = periodic_hann(N_FFT, sym=False).astype(np.float32)
        self.window_stft = window
        self.freq_pad = np.zeros([1, self.dim_c, self.n_bins - self.dim_f, self.dim_t], dtype=np.float32)

    def stft(self, x):
        x = x.reshape(-1, self.chunk_size)
        results = []
        for i in range(x.shape[0]):
            Z = librosa.stft(
                x[i].numpy() if hasattr(x[i], 'numpy') else x[i],
                n_fft=self.n_fft,
                hop_length=self.hop,
                window=self.window_stft,
                center=True,
            )
            Z_real = np.real(Z)
            Z_imag = np.imag(Z)
            results.append(np.stack([Z_real, Z_imag], axis=-1))
        X = np.stack(results)  # (batch, n_bins, dim_t, 2)
        X = X.transpose(0, 3, 1, 2)  # (batch, 2, n_bins, dim_t)
        X = X.reshape(-1, 2, self.n_bins, self.dim_t)
        X = X.reshape(-1, self.dim_c, self.n_bins, self.dim_t)
        return X[:, :, :self.dim_f, :]

    def istft(self, x, freq_pad=None):
        if freq_pad is None:
            freq_pad = np.repeat(self.freq_pad, x.shape[0], axis=0)
        x = np.concatenate([x, freq_pad], axis=-2)
        x = x.reshape(-1, HALF_DIM_C, 2, self.n_bins, self.dim_t)
        x = x.reshape(-1, 2, self.n_bins, self.dim_t)
        x = x.transpose(0, 2, 3, 1)  # (batch, n_bins, dim_t, 2)
        results = []
        for i in range(x.shape[0]):
            Z = x[i, :, :, 0] + 1j * x[i, :, :, 1]
            wav = librosa.istft(
                Z,
                hop_length=self.hop,
                window=self.window_stft,
                center=True,
                length=self.chunk_size,
            )
            results.append(wav)
        result = np.stack(results)
        result = result.reshape(-1, HALF_DIM_C, self.chunk_size)
        return result


def separate_vocals(audio_path, output_dir, progress_callback=None, is_cancelled=None):
    if not os.path.exists(audio_path):
        return None, None

    if progress_callback:
        progress_callback(2, "Đang mở file âm thanh và nạp mô hình AI...")

    os.makedirs(output_dir, exist_ok=True)
    session = _get_session()
    model = _STFT()

    audio, sr = sf.read(audio_path, dtype="float32")
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=0)
    else:
        audio = audio.T
        if audio.shape[0] == 1:
            audio = np.repeat(audio, 2, axis=0)
        elif audio.shape[0] > 2:
            audio = audio[:2]

    if sr != SR:
        from scipy.signal import resample_poly
        gcd_val = np.gcd(sr, SR)
        up = SR // gcd_val
        down = sr // gcd_val
        audio = resample_poly(audio.astype(np.float64), up, down, axis=1).astype(np.float32)

    samples = audio.shape[-1]
    margin = SR
    chunk_size = 15 * SR

    if samples < chunk_size:
        chunk_size = samples
    if margin > chunk_size:
        margin = chunk_size

    segments = {}
    counter = -1
    for skip in range(0, samples, chunk_size):
        counter += 1
        s_margin = 0 if counter == 0 else margin
        end = min(skip + chunk_size + margin, samples)
        start = skip - s_margin
        segments[skip] = audio[:, start:end].copy()
        if end == samples:
            break

    total_segments = max(1, len(segments))
    if progress_callback:
        progress_callback(5, f"Bắt đầu tách giọng & nhạc (0/{total_segments} đoạn)...")

    chunked_sources = []
    for chunk_idx, mix_start in enumerate(segments):
        if is_cancelled and is_cancelled():
            return None, None

        cmix = segments[mix_start]
        sources = []
        n_sample = cmix.shape[1]
        trim = model.n_fft // 2
        gen_size = model.chunk_size - 2 * trim
        pad = gen_size - n_sample % gen_size
        if pad == gen_size:
            pad = 0

        mix_p = np.concatenate([
            np.zeros((2, trim), dtype=np.float32),
            cmix,
            np.zeros((2, pad), dtype=np.float32),
            np.zeros((2, trim), dtype=np.float32),
        ], axis=1)

        mix_waves = []
        i = 0
        while i < n_sample + pad:
            waves = mix_p[:, i:i + model.chunk_size]
            mix_waves.append(waves)
            i += gen_size

        if not mix_waves:
            continue

        mix_waves = np.array(mix_waves, dtype=np.float32)

        spek = model.stft(mix_waves)

        spec_pred = session.run(None, {"input": spek})[0]

        tar_waves = model.istft(spec_pred)

        tar_signal = tar_waves[:, :, trim:-trim]
        tar_signal = tar_signal.transpose(1, 0, 2).reshape(2, -1)

        tar_signal = tar_signal[:, :n_sample + pad]

        start = 0 if mix_start == 0 else margin
        end = None if mix_start == list(segments.keys())[-1] else -margin
        if margin == 0:
            end = None

        sources.append(tar_signal[:, start:end])
        chunked_sources.append(sources)

        if progress_callback:
            chunk_pct = 5 + int(((chunk_idx + 1) / total_segments) * 87)
            progress_callback(
                chunk_pct,
                f"Đang tách âm thanh AI: {chunk_idx + 1}/{total_segments} đoạn ({chunk_pct}%)"
            )

    if not chunked_sources:
        return None, None

    if progress_callback:
        progress_callback(93, "Đang hòa trộn các dải âm...")

    vocals_441 = np.concatenate([s[0] for s in chunked_sources], axis=-1)[:, :samples]

    if sr != SR:
        from scipy.signal import resample_poly
        gcd_val = np.gcd(SR, sr)
        up = sr // gcd_val
        down = SR // gcd_val
        vocals_441 = resample_poly(vocals_441.astype(np.float64), up, down, axis=1).astype(np.float32)

    audio_orig, orig_sr = sf.read(audio_path, dtype="float32")
    if audio_orig.ndim == 1:
        audio_orig = audio_orig
    else:
        audio_orig = audio_orig[:, 0]

    vocals_mono = vocals_441[0]
    if len(vocals_mono) < len(audio_orig):
        vocals_mono = np.pad(vocals_mono, (0, len(audio_orig) - len(vocals_mono)))
    else:
        vocals_mono = vocals_mono[:len(audio_orig)]

    # Model outputs instrumental; vocals = original - instrumental
    instrumental = vocals_mono
    vocals_final = audio_orig - instrumental

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    result_dir = os.path.join(output_dir, "onnx_separated", base_name)
    os.makedirs(result_dir, exist_ok=True)

    if progress_callback:
        progress_callback(96, "Đang lưu Voice.wav và Music.wav...")

    vocal_out = os.path.join(result_dir, "Voice.wav")
    music_out = os.path.join(result_dir, "Music.wav")
    sf.write(vocal_out, vocals_final, orig_sr)
    sf.write(music_out, instrumental, orig_sr)

    # Legacy aliases
    legacy_vocal = os.path.join(result_dir, "vocals.wav")
    legacy_music = os.path.join(result_dir, "no_vocals.wav")
    if not os.path.exists(legacy_vocal):
        try:
            os.link(vocal_out, legacy_vocal)
        except Exception:
            sf.write(legacy_vocal, vocals_final, orig_sr)
    if not os.path.exists(legacy_music):
        try:
            os.link(music_out, legacy_music)
        except Exception:
            sf.write(legacy_music, instrumental, orig_sr)

    if progress_callback:
        progress_callback(100, "Hoàn tất tách Voice.wav & Music.wav")

    return vocal_out, music_out
