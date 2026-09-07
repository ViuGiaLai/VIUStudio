from vocal_processor import separate_vocals


class DemucsAdapter:
    """Vocal/instrumental separation using ONNX Runtime (UVR MDX-NET model)."""

    def separate(self, audio_path: str, output_dir: str, progress_callback=None, is_cancelled=None):
        return separate_vocals(
            audio_path,
            output_dir,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
        )
