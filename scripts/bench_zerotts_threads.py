"""Measure ZeroTTS CPU throughput for worker/thread settings.

Direct model mode (``workers:intra:codec`` specs):
    python scripts/bench_zerotts_threads.py 3:4:4 6:2:2

Full application path (``app[:workers]``), which is what the Voice workflow
runs — it also proves the env overrides reach the runtime:
    python scripts/bench_zerotts_threads.py app
"""

import os
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "app"), os.path.join(ROOT, "ui"), ROOT]

MODEL_DIR = os.path.join(ROOT, "models", "zerotts")
TEMP_DIR = os.path.join(ROOT, "temp", "bench_zerotts")
CUES = [
    "Xin chào các bạn, hôm nay chúng ta sẽ cùng nhau tìm hiểu một chủ đề rất thú vị.",
    "Đây là câu thứ hai dùng để đo tốc độ tổng hợp giọng nói trên máy này.",
    "Câu thứ ba ngắn hơn.",
    "Trong video này, tôi sẽ hướng dẫn từng bước để bạn có thể làm theo một cách dễ dàng.",
    "Cảm ơn các bạn đã theo dõi, hãy nhấn like và đăng ký kênh để ủng hộ mình nhé.",
    "Hẹn gặp lại các bạn trong video tiếp theo.",
]


def _wav_seconds(path):
    with wave.open(path, "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def run_model(workers, intra, codec):
    import zerotts

    t0 = time.perf_counter()
    model = zerotts.ZeroTTS(
        MODEL_DIR,
        intra_op_num_threads=intra,
        codec_intra_op_num_threads=codec,
        warmup=True,
    )
    load_seconds = time.perf_counter() - t0

    def job(text):
        return model.synthesize(text, voice="maichi").shape[-1] / model.sample_rate

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        audio_seconds = sum(executor.map(job, CUES))
    report(f"workers={workers} intra={intra} codec={codec}", load_seconds, time.perf_counter() - t0, audio_seconds)


def run_app(workers=None):
    import tts_processor
    from zerotts_support import codec_threads, synth_threads, synth_workers

    os.makedirs(TEMP_DIR, exist_ok=True)
    workers = workers or synth_workers(len(CUES))

    def job(item):
        index, text = item
        target = os.path.join(TEMP_DIR, f"cue_{index}.wav")
        tts_processor.synthesize_text_to_wav_16k_mono(
            text=text,
            wav_path=target,
            voice="zerotts:maichi",
            speed=1.0,
            tmp_dir=TEMP_DIR,
        )
        return _wav_seconds(target)

    t0 = time.perf_counter()
    # The model loads lazily inside the first cues, exactly like the workflow.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        audio_seconds = sum(executor.map(job, enumerate(CUES)))
    report(
        f"app path workers={workers} intra={synth_threads()} codec={codec_threads()}",
        float("nan"),
        time.perf_counter() - t0,
        audio_seconds,
    )


def report(label, load_seconds, synth_seconds, audio_seconds):
    load = "   n/a" if load_seconds != load_seconds else f"{load_seconds:5.1f}s"
    print(
        f"{label} | load={load} synth={synth_seconds:5.1f}s | audio={audio_seconds:5.2f}s "
        f"| {audio_seconds / synth_seconds:.2f}x realtime",
        flush=True,
    )


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        if spec == "app" or spec.startswith("app:"):
            parts = spec.split(":")
            run_app(int(parts[1]) if len(parts) > 1 else None)
        else:
            run_model(*(int(part) for part in spec.split(":")))
