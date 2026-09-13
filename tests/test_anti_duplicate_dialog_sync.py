import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "ui"), os.path.join(ROOT, "app"), ROOT]
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from app.anti_duplicate import AntiDuplicateSettings, build_anti_duplicate_audio_filter, build_anti_duplicate_video_chain
from ui.dialogs.anti_duplicate_custom_dialog import AntiDuplicateCustomDialog


class AntiDuplicateDialogSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, AntiDuplicateCustomDialog):
                widget.close()
                widget.deleteLater()
        self.app.processEvents()

    def test_every_editable_control_is_saved_to_export_settings(self):
        dialog = AntiDuplicateCustomDialog(AntiDuplicateSettings(enabled=True))
        dialog.radio_flip_none.setChecked(True)
        dialog.radio_color_random.setChecked(True)
        dialog.radio_layout_ambient.setChecked(True)
        dialog.zoom_cb.setChecked(False)
        dialog.punch_zoom_cb.setChecked(False)
        dialog.vignette_cb.setChecked(False)
        dialog.grain_cb.setChecked(False)
        dialog.unsharp_cb.setChecked(False)
        dialog.speed_cb.setChecked(False)
        dialog.pitch_cb.setChecked(False)
        dialog.eq_cb.setChecked(False)
        dialog.vol_cb.setChecked(False)
        dialog.meta_cb.setChecked(False)
        dialog.marquee_cb.setChecked(True)
        dialog.marquee_text_edit.setText("SYNC TEST")
        dialog.radio_dir_ltr.setChecked(True)
        dialog.marquee_speed_combo.setCurrentIndex(dialog.marquee_speed_combo.findData(160))

        dialog._save_and_close()
        settings = dialog.settings

        self.assertFalse(settings.allow_horizontal_flip)
        self.assertEqual(settings.flip_mode, "none")
        self.assertTrue(settings.random_color_grade)
        self.assertEqual(settings.color_grading_mode, "random")
        self.assertEqual(settings.visual_layout_mode, "ambient_frame")
        self.assertFalse(settings.add_zoom)
        self.assertFalse(settings.add_punch_zoom)
        self.assertEqual(settings.geometric_mode, "none")
        self.assertFalse(settings.add_grain_noise)
        self.assertFalse(settings.add_unsharp)
        self.assertFalse(settings.add_micro_speed)
        self.assertFalse(settings.add_pitch_shift)
        self.assertFalse(settings.add_eq_audio)
        self.assertFalse(settings.add_volume_level)
        self.assertFalse(settings.poison_metadata)
        self.assertEqual(settings.marquee_text, "SYNC TEST")
        self.assertEqual(settings.marquee_direction, "left_to_right")
        self.assertEqual(settings.marquee_speed, 160)

        video_chain = build_anti_duplicate_video_chain(settings, 1920, 1080, 600)
        audio_chain = build_anti_duplicate_audio_filter(settings)
        self.assertNotIn("hflip", video_chain)
        self.assertNotIn("noise=", video_chain)
        self.assertNotIn("cas=", video_chain)
        self.assertIn("pad=1920:1080", video_chain)
        self.assertIn("SYNC TEST", video_chain)
        self.assertEqual(audio_chain, "")

    def test_cancel_does_not_mutate_the_live_export_settings(self):
        source = AntiDuplicateSettings(
            enabled=True,
            marquee_text="ORIGINAL",
        )
        before = source.to_dict()
        dialog = AntiDuplicateCustomDialog(source)

        dialog.marquee_text_edit.setText("CHANGED")
        dialog.reject()

        self.assertEqual(source.to_dict(), before)

    def test_every_disabled_control_stays_disabled_after_reopen(self):
        dialog = AntiDuplicateCustomDialog(AntiDuplicateSettings(enabled=True))
        dialog.radio_flip_none.setChecked(True)
        dialog.radio_color_none.setChecked(True)
        dialog.radio_layout_none.setChecked(True)
        for checkbox in (
            dialog.zoom_cb,
            dialog.punch_zoom_cb,
            dialog.marquee_cb,
            dialog.vignette_cb,
            dialog.grain_cb,
            dialog.unsharp_cb,
            dialog.speed_cb,
            dialog.pitch_cb,
            dialog.eq_cb,
            dialog.vol_cb,
            dialog.meta_cb,
        ):
            checkbox.setChecked(False)

        dialog._save_and_close()
        saved = AntiDuplicateSettings.from_dict(dialog.settings.to_dict())
        reopened = AntiDuplicateCustomDialog(saved)

        self.assertTrue(reopened.radio_flip_none.isChecked())
        self.assertTrue(reopened.radio_color_none.isChecked())
        self.assertTrue(reopened.radio_layout_none.isChecked())
        self.assertTrue(all(not checkbox.isChecked() for checkbox in (
            reopened.zoom_cb,
            reopened.punch_zoom_cb,
            reopened.marquee_cb,
            reopened.vignette_cb,
            reopened.grain_cb,
            reopened.unsharp_cb,
            reopened.speed_cb,
            reopened.pitch_cb,
            reopened.eq_cb,
            reopened.vol_cb,
            reopened.meta_cb,
        )))
        self.assertEqual(
            build_anti_duplicate_video_chain(saved, 1920, 1080, 60),
            "setsar=1",
        )
        self.assertEqual(build_anti_duplicate_audio_filter(saved), "")


if __name__ == "__main__":
    unittest.main()
