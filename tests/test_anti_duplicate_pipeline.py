import os
import sys

_app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import unittest
from unittest.mock import MagicMock, patch

from app.anti_duplicate import (
    AntiDuplicateSettings,
    build_anti_duplicate_video_chain,
    build_anti_duplicate_audio_filter,
    get_metadata_poison_args,
    apply_anti_duplicate_to_command,
    build_marquee_text_filter,
)
from app.video_processor import _build_logo_overlay_command, embed_ass_subtitles
from app.workflows.export_workflow import ExportWorkflow


class TestAntiDuplicatePipeline(unittest.TestCase):
    def test_settings_default_values(self):
        s = AntiDuplicateSettings(enabled=True)
        self.assertTrue(s.enabled)
        self.assertEqual(s.zoom_percent, 5.0)
        self.assertTrue(s.random_color_grade)
        self.assertEqual(s.geometric_mode, "both")
        self.assertEqual(s.pitch_shift_semitones, 2.0)
        self.assertTrue(s.poison_metadata)
        # New KT#6-9 fields
        self.assertTrue(s.add_grain_noise)
        self.assertTrue(s.add_micro_speed)
        self.assertEqual(s.crop_offset_px, 3)
        self.assertTrue(s.add_eq_audio)
        # New KT#10-11 fields
        self.assertTrue(s.add_unsharp)
        self.assertTrue(s.add_volume_level)
        # 4-Tone Periodic Color Grading fields
        self.assertEqual(s.color_grading_mode, "periodic")
        self.assertEqual(s.color_cycle_seconds, 240)

    def test_video_chain_generation(self):
        s = AntiDuplicateSettings(enabled=True)
        chain = build_anti_duplicate_video_chain(s)
        self.assertIn("scale=iw*1.05", chain)
        self.assertIn("crop=iw/1.05", chain)
        self.assertIn("vignette=", chain)
        # Default is 4-tone periodic color grading
        self.assertIn("between(mod(t,960)", chain)

        # Random mode produces legacy brightness/contrast eq
        s_random = AntiDuplicateSettings(enabled=True, color_grading_mode="random")
        chain_random = build_anti_duplicate_video_chain(s_random)
        self.assertIn("eq=brightness=", chain_random)

    def test_audio_filter_generation(self):
        s = AntiDuplicateSettings(enabled=True)
        af = build_anti_duplicate_audio_filter(s)
        self.assertIn("asetrate=", af)
        self.assertIn("aresample=44100", af)
        self.assertIn("atempo=", af)

    def test_metadata_poison_args(self):
        s = AntiDuplicateSettings(enabled=True)
        meta = get_metadata_poison_args(s)
        self.assertIn("-map_metadata", meta)
        self.assertIn("-1", meta)
        self.assertTrue(any("encoder=VIUStudio" in x for x in meta))

    def test_apply_to_command(self):
        s = AntiDuplicateSettings(enabled=True)
        cmd = ["ffmpeg", "-i", "input.mp4", "-c:v", "libx264", "out.mp4"]
        apply_anti_duplicate_to_command(cmd, s, output_path="out.mp4")
        self.assertEqual(cmd[-1], "out.mp4")
        self.assertIn("-map_metadata", cmd)
        self.assertIn("-af", cmd)

    def test_export_workflow_run_signature(self):
        import inspect
        sig = inspect.signature(ExportWorkflow.run)
        self.assertIn("anti_duplicate_enabled", sig.parameters)

    def test_continuous_auto_recap_video_chain(self):
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, allow_horizontal_flip=True)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        # Cac ky thuat goc
        self.assertIn("hflip", chain)
        self.assertIn("crop=w=", chain)
        self.assertIn("scale=1920:1080", chain)
        self.assertIn("hue=h=", chain)
        self.assertIn("setsar=1", chain)
        # KT#8: Crop offset 3px (x/y dich khoi trung tam)
        self.assertIn("+3", chain)
        # KT#6: Grain noise
        self.assertIn("noise=alls=8", chain)
        self.assertIn("allf=t+u", chain)
        # KT#10: Unsharp nhe
        self.assertIn("unsharp=3:3:0.5:3:3:0", chain)
        # KT#7: Micro speed variation
        self.assertIn("setpts=0.9999*PTS", chain)

    def test_continuous_auto_recap_audio_filter(self):
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True)
        af = build_anti_duplicate_audio_filter(s)
        # KT#5: Pitch shift
        self.assertIn("asetrate=44761", af)
        self.assertIn("aresample=44100", af)
        self.assertIn("atempo=0.985222", af)
        # KT#9: Audio EQ
        self.assertIn("equalizer=f=1200", af)
        self.assertIn("equalizer=f=5500", af)
        # KT#11: Volume level
        self.assertIn("volume=0.97", af)
        # KT#7: Micro speed compensation
        self.assertIn("atempo=1.0001", af)


    def test_crop_offset_safety(self):
        """Kiem tra offset crop khong lech ra ngoai vung an toan."""
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, crop_offset_px=3)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        # crop_w = 1920*0.95 = 1824, margin = (1920-1824)/2 = 48px >> 3px offset -> an toan
        # Kiem tra crop co offset +3
        self.assertIn("(iw-ow)/2+3", chain)
        self.assertIn("(ih-oh)/2+3", chain)

    def test_grain_noise_not_in_non_continuous_mode(self):
        """KT#6 chi ap dung khi continuous_mode=True."""
        s = AntiDuplicateSettings(enabled=True, continuous_mode=False)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertNotIn("noise=alls=8", chain)
        self.assertNotIn("setpts=0.9999", chain)

    def test_micro_speed_audio_compensation(self):
        """KT#7: atempo=1.0001 phai co trong audio de bu tru setpts=0.9999 tren video."""
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True)
        af = build_anti_duplicate_audio_filter(s)
        self.assertIn("atempo=1.0001", af)
        # Video chain cung phai co setpts
        vc = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertIn("setpts=0.9999*PTS", vc)

    def test_timeline_sequence_export_signature(self):
        import inspect
        from app.services.timeline_sequence_export import export_timeline_sequence
        sig = inspect.signature(export_timeline_sequence)
        self.assertIn("anti_duplicate_enabled", sig.parameters)
        self.assertIn("anti_duplicate_settings", sig.parameters)

    def test_custom_settings_serialization(self):
        s = AntiDuplicateSettings(enabled=True, allow_horizontal_flip=False, add_zoom=False, color_grading_mode="periodic", color_cycle_seconds=240)
        d = s.to_dict()
        self.assertFalse(d["allow_horizontal_flip"])
        self.assertFalse(d["add_zoom"])
        self.assertEqual(d["color_grading_mode"], "periodic")
        self.assertEqual(d["color_cycle_seconds"], 240)
        restored = AntiDuplicateSettings.from_dict(d)
        self.assertFalse(restored.allow_horizontal_flip)
        self.assertFalse(restored.add_zoom)
        self.assertEqual(restored.color_grading_mode, "periodic")
        self.assertEqual(restored.color_cycle_seconds, 240)
        self.assertTrue(restored.enabled)
        summary = restored.summary_text()
        self.assertIn("Tắt lật", summary)
        self.assertIn("Zoom", summary)

    def test_custom_disable_horizontal_flip(self):
        # Khi user tat phan chieu / lat guong (allow_horizontal_flip=False)
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, allow_horizontal_flip=False)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertNotIn("hflip", chain)
        # Nhung cac filter khac van hoat dong day du
        self.assertIn("crop=w=", chain)
        self.assertIn("noise=alls=8", chain)
        self.assertIn("unsharp=3:3:0.5:3:3:0", chain)

    def test_custom_disable_zoom_and_pitch(self):
        # Khi user tat zoom va tat pitch shift
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, add_zoom=False, add_pitch_shift=False)
        vc = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertNotIn("crop=w=", vc)
        af = build_anti_duplicate_audio_filter(s)
        self.assertNotIn("asetrate=", af)
        # Nhung cac filter khac nhu EQ, noise van hoat dong
        self.assertIn("equalizer=", af)
        self.assertIn("noise=alls=8", vc)

    def test_periodic_flip_filter_generation(self):
        # Cach 2: 4 phut xuoi / 1 phut lat (chu ky 300s, enable tu 240 den 300) cho video mac dinh
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, flip_mode="periodic", flip_normal_seconds=240, flip_duration_seconds=60)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertIn("hflip=enable='between(mod(t,300),240,300)'", chain)
        
        # Test tu dong thich ung cho video ngan (vi du 120s = 2 phut): chu ky co ve 60s (48s xuoi / 12s lat)
        chain_short = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080, total_duration=120.0)
        self.assertIn("hflip=enable='between(mod(t,60),48,60)'", chain_short)
        
        # Kiem tra summary text
        summary = s.summary_text()
        self.assertIn("80% xuôi/20% lật", summary)

    def test_always_flip_filter_generation(self):
        # Che do lat 100% video
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, flip_mode="always")
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertIn("hflip,", chain)
        self.assertNotIn("hflip=enable", chain)

    def test_none_flip_filter_generation(self):
        # Che do tat lat hoan toan
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, flip_mode="none")
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertNotIn("hflip", chain)

    def test_periodic_color_grade_generation(self):
        # De xuat 1 (Nang cap do sau 10-12%): Xoay vong 4 tone mau dien anh moi 4 phut (960s chu ky)
        s = AntiDuplicateSettings(enabled=True, continuous_mode=True, color_grading_mode="periodic", color_cycle_seconds=240)
        chain = build_anti_duplicate_video_chain(s, target_w=1920, target_h=1080)
        self.assertIn("eq=gamma_r=1.10:gamma_b=0.90:saturation=1.08:contrast=1.03:enable='between(mod(t,960),0,240)'", chain)
        self.assertIn("eq=gamma_r=0.88:gamma_b=1.12:saturation=1.05:contrast=1.04:enable='between(mod(t,960),240,480)'", chain)
        self.assertIn("eq=contrast=1.08:brightness=-0.015:saturation=1.10:gamma=0.96:enable='between(mod(t,960),480,720)'", chain)
        self.assertIn("eq=contrast=0.95:gamma=1.05:saturation=0.90:gamma_g=1.04:gamma_r=1.02:enable='between(mod(t,960),720,960)'", chain)

    def test_disable_color_grade(self):
        # Tat mau qua random_color_grade=False hoac color_grading_mode="none"
        s1 = AntiDuplicateSettings(enabled=True, continuous_mode=True, random_color_grade=False)
        chain1 = build_anti_duplicate_video_chain(s1, target_w=1920, target_h=1080)
        self.assertNotIn("eq=", chain1)

        s2 = AntiDuplicateSettings(enabled=True, continuous_mode=True, color_grading_mode="none")
        chain2 = build_anti_duplicate_video_chain(s2, target_w=1920, target_h=1080)
        self.assertNotIn("eq=", chain2)

    def test_visual_layout_modes(self):
        # 1. Letterbox (Chuan dien anh 2.05:1 Univisium - Mo nhe chuyen tiep, BỎ HẾT ĐƯỜNG VIỀN)
        s_letterbox = AntiDuplicateSettings(enabled=True, continuous_mode=True, visual_layout_mode="letterbox")
        chain_lb = build_anti_duplicate_video_chain(s_letterbox, target_w=1920, target_h=1080)
        # Bar height = 1080 * 0.0667 = 72px (chi 6.6% moi ben, mo nhe chuyen tiep 30% -> 18% -> 6%)
        self.assertIn("color=black@0.30:t=fill", chain_lb)
        self.assertIn("color=black@0.18:t=fill", chain_lb)
        self.assertIn("color=black@0.06:t=fill", chain_lb)
        # Bo hoan toan cac duong vien mau vang cam sac canh
        self.assertNotIn("0xf59e0b", chain_lb)

        # 2. Ambient Frame (Bo goc 92% + vien Slate/Cyan)
        s_ambient = AntiDuplicateSettings(enabled=True, continuous_mode=True, visual_layout_mode="ambient_frame")
        chain_amb = build_anti_duplicate_video_chain(s_ambient, target_w=1920, target_h=1080)
        self.assertIn("scale=1766:992", chain_amb)
        self.assertIn("pad=1920:1080:77:44:color=0x0f172a", chain_amb)
        self.assertIn("color=0x38bdf8@0.70:t=2", chain_amb)

        # 3. Ken Burns (Dynamic Slow Pan & Micro Drift)
        s_kb = AntiDuplicateSettings(enabled=True, continuous_mode=True, visual_layout_mode="ken_burns")
        chain_kb = build_anti_duplicate_video_chain(s_kb, target_w=1920, target_h=1080)
        self.assertIn("crop=w='1824':h='1026'", chain_kb)
        self.assertIn("sin(2*3.14159265358979*t/60)", chain_kb)

        # 4. Light Leak (Vet sang quang hoc & hat bui)
        s_leak = AntiDuplicateSettings(enabled=True, continuous_mode=True, visual_layout_mode="light_leak")
        chain_leak = build_anti_duplicate_video_chain(s_leak, target_w=1920, target_h=1080)
        self.assertIn("vignette=angle='PI/5+PI/20*sin", chain_leak)
        self.assertIn("x0='w*0.82':y0='h*0.18'", chain_leak)

        # 5. None (Giu nguyen 16:9 goc)
        s_none = AntiDuplicateSettings(enabled=True, continuous_mode=True, visual_layout_mode="none")
        chain_none = build_anti_duplicate_video_chain(s_none, target_w=1920, target_h=1080)
        self.assertNotIn("drawbox=", chain_none)
        self.assertNotIn("pad=", chain_none)

    def test_visual_layout_serialization_and_summary(self):
        s = AntiDuplicateSettings(enabled=True, visual_layout_mode="ambient_frame")
        d = s.to_dict()
        self.assertEqual(d["visual_layout_mode"], "ambient_frame")
        restored = AntiDuplicateSettings.from_dict(d)
        self.assertEqual(restored.visual_layout_mode, "ambient_frame")
        self.assertIn("Viền Ambient", restored.summary_text())

        s_kb = AntiDuplicateSettings(enabled=True, visual_layout_mode="ken_burns")
        self.assertIn("Lia máy", s_kb.summary_text())

        s_leak = AntiDuplicateSettings(enabled=True, visual_layout_mode="light_leak")
        self.assertIn("Vệt sáng", s_leak.summary_text())

        s_none = AntiDuplicateSettings(enabled=True, visual_layout_mode="none")
        self.assertIn("Bố cục 16:9", s_none.summary_text())

    def test_marquee_running_text_filters(self):
        # 1. Right to Left (Mac dinh)
        s_rtl = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            marquee_enabled=True,
            marquee_text="VIURECAP",
            marquee_direction="right_to_left",
            marquee_speed=150,
        )
        chain_rtl = build_anti_duplicate_video_chain(s_rtl, target_w=1920, target_h=1080)
        self.assertIn("drawtext=", chain_rtl)
        self.assertIn("text='VIURECAP'", chain_rtl)
        self.assertIn("w-mod(t*150", chain_rtl)

        # 2. Left to Right
        s_ltr = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            marquee_enabled=True,
            marquee_text="VIURECAP",
            marquee_direction="left_to_right",
            marquee_speed=120,
        )
        chain_ltr = build_anti_duplicate_video_chain(s_ltr, target_w=1920, target_h=1080)
        self.assertIn("drawtext=", chain_ltr)
        self.assertIn("-text_w+mod(t*120", chain_ltr)

        # 3. Marquee disabled
        s_off = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            marquee_enabled=False,
        )
        chain_off = build_anti_duplicate_video_chain(s_off, target_w=1920, target_h=1080)
        self.assertNotIn("drawtext=", chain_off)

    def test_marquee_serialization(self):
        s_default = AntiDuplicateSettings()
        self.assertEqual(s_default.marquee_speed, 70)

        s = AntiDuplicateSettings(
            enabled=True,
            marquee_enabled=True,
            marquee_text="TEST MARQUEE",
            marquee_direction="left_to_right",
            marquee_speed=45,
        )
        d = s.to_dict()
        self.assertTrue(d["marquee_enabled"])
        self.assertEqual(d["marquee_text"], "TEST MARQUEE")
        self.assertEqual(d["marquee_direction"], "left_to_right")
        self.assertEqual(d["marquee_speed"], 45)

        restored = AntiDuplicateSettings.from_dict(d)
        self.assertTrue(restored.marquee_enabled)
        self.assertEqual(restored.marquee_text, "TEST MARQUEE")
        self.assertEqual(restored.marquee_direction, "left_to_right")
        self.assertEqual(restored.marquee_speed, 45)

    def test_music_camouflage_filter(self):
        """KT#13: Music Camouflage (aecho + afreqshift) khi add_music_camouflage=True."""
        # Khi bật: audio filter phải chứa aecho và afreqshift
        s = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            add_music_camouflage=True,
        )
        af = build_anti_duplicate_audio_filter(s)
        self.assertIn("aecho", af, "Music camouflage: aecho filter phải có mặt khi bật")
        self.assertIn("afreqshift", af, "Music camouflage: afreqshift filter phải có mặt khi bật")

        # Khi tắt (mặc định): không có aecho/afreqshift
        s_off = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            add_music_camouflage=False,
        )
        af_off = build_anti_duplicate_audio_filter(s_off)
        self.assertNotIn("aecho", af_off, "Khi tắt music camouflage không được có aecho")
        self.assertNotIn("afreqshift", af_off, "Khi tắt music camouflage không được có afreqshift")

        # Serialization
        d = s.to_dict()
        self.assertTrue(d["add_music_camouflage"])
        restored = AntiDuplicateSettings.from_dict(d)
        self.assertTrue(restored.add_music_camouflage)

    def test_summary_text_shows_marquee_text(self):
        """summary_text() phải hiển thị marquee_text để user kiểm tra trước khi xuất."""
        s = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            marquee_enabled=True,
            marquee_text="MY BRAND",
        )
        summary = s.summary_text()
        self.assertIn("MY BRAND", summary, "summary_text() phải hiển thị marquee_text")
        self.assertIn("Chữ:", summary)

        # Khi marquee tắt: không hiển thị text
        s2 = AntiDuplicateSettings(
            enabled=True,
            continuous_mode=True,
            marquee_enabled=False,
            marquee_text="HIDDEN TEXT",
        )
        summary2 = s2.summary_text()
        self.assertNotIn("HIDDEN TEXT", summary2, "Khi marquee tắt không hiển thị marquee text trong summary")


if __name__ == "__main__":
    unittest.main()
