"""Curated Microsoft Edge TTS voices exposed by VIUStudio.

The service contains many locales and voices.  VIUStudio deliberately exposes
the Vietnamese voices plus a compact English narration/recap set so the Voice
picker stays useful instead of becoming an unfiltered service dump.
"""

from __future__ import annotations


EDGE_TTS_VOICES = (
    # Vietnamese
    ("vi-VN-HoaiMyNeural", "Hoài My — Friendly", "vi", "female", ("general", "friendly")),
    ("vi-VN-NamMinhNeural", "Nam Minh — Friendly", "vi", "male", ("general", "friendly")),
    # English — American narration, news, novels and conversational delivery.
    ("en-US-AriaNeural", "Aria — News / Novel (US)", "en", "female", ("news", "novel", "confident")),
    ("en-US-MichelleNeural", "Michelle — News / Novel (US)", "en", "female", ("news", "novel", "pleasant")),
    ("en-US-JennyNeural", "Jenny — Friendly (US)", "en", "female", ("general", "friendly", "comfort")),
    ("en-US-AvaNeural", "Ava — Expressive (US)", "en", "female", ("conversation", "expressive")),
    ("en-US-EmmaNeural", "Emma — Clear / Conversational (US)", "en", "female", ("conversation", "clear")),
    ("en-US-ChristopherNeural", "Christopher — Authoritative (US)", "en", "male", ("news", "novel", "authority")),
    ("en-US-GuyNeural", "Guy — Passionate (US)", "en", "male", ("news", "novel", "passionate")),
    ("en-US-RogerNeural", "Roger — Lively (US)", "en", "male", ("news", "novel", "lively")),
    ("en-US-AndrewNeural", "Andrew — Warm / Confident (US)", "en", "male", ("conversation", "warm", "confident")),
    ("en-US-EricNeural", "Eric — Rational (US)", "en", "male", ("news", "novel", "rational")),
    # English — British alternatives.
    ("en-GB-SoniaNeural", "Sonia — Friendly (UK)", "en", "female", ("general", "friendly", "british")),
    ("en-GB-LibbyNeural", "Libby — Positive (UK)", "en", "female", ("general", "positive", "british")),
    ("en-GB-RyanNeural", "Ryan — Friendly (UK)", "en", "male", ("general", "friendly", "british")),
    ("en-GB-ThomasNeural", "Thomas — Positive (UK)", "en", "male", ("general", "positive", "british")),
)


def catalog_entries() -> list[dict]:
    return [
        {
            "id": f"edge:{voice_id}",
            "name": f"{display_name} (Edge Online)",
            "provider": "edge",
            "provider_voice": voice_id,
            "language": language,
            "gender": gender,
            "tier": "free",
            "preview_video_url": "",
            "preview_video_path": "",
            "preview_audio_url": "",
            "preview_audio_path": "",
            "enabled": True,
            "tags": ["online", "edge", *tags],
        }
        for voice_id, display_name, language, gender, tags in EDGE_TTS_VOICES
    ]
