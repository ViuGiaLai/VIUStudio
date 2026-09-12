from __future__ import annotations
import hashlib, os, random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

@dataclass
class AntiDuplicateSettings:
    """Cau hinh cho cac ky thuat chong nhan dien video trung lap (Content ID)."""
    enabled: bool = False
    zoom_percent: float = 5.0
    random_color_grade: bool = True
    # Che do chinh mau: "periodic" (Xoay vong 4 tone dien anh moi 4 phut - De xuat 1), "random" (1 mau co dinh), "none" (tat)
    color_grading_mode: str = "periodic"
    color_cycle_seconds: int = 240  # 4 phut cho moi tone mau
    color_seed: Optional[int] = None
    geometric_mode: str = "both"
    pitch_shift_semitones: float = 2.0
    pitch_seed: Optional[int] = None
    poison_metadata: bool = True
    project_name: str = "VIUStudio"
    allow_horizontal_flip: bool = True
    # Che do lat: "periodic" (Xen ke 4p xuoi / 1p lat), "always" (Lat 100%), "none" (Tat hoan toan)
    flip_mode: str = "periodic"
    flip_normal_seconds: int = 240  # 4 phut xuoi
    flip_duration_seconds: int = 60  # 1 phut lat
    continuous_mode: bool = False
    target_width: int = 1920
    target_height: int = 1080
    # KT#6: Grain noise nhe (pha perceptual hash / DCT fingerprint YouTube)
    add_grain_noise: bool = True
    # KT#7: Micro speed variation 0.01% (pha nhip thoi gian / scene cut signature)
    add_micro_speed: bool = True
    # KT#8: Crop offset (px) - dich khung cat khoi trung tam -> pha DCT block boundary
    crop_offset_px: int = 3
    # KT#9: Audio EQ nhe (pha Chromaprint / Shazam audio fingerprint)
    add_eq_audio: bool = True
    # KT#10: Unsharp nhe (pha perceptual hash pixel-level - cạnh sắc nét hon 1 chut)
    add_unsharp: bool = True
    # KT#11: Volume -0.3dB (pha audio level fingerprint Shazam / ACRCloud)
    add_volume_level: bool = True
    # Khi True: bo qua toan bo audio filter (pitch/EQ/volume) vi audio track
    # da la TTS/dub - chi can pha nhan dien video, khong duoc bien dang giong doc.
    skip_audio_filter: bool = False
    # Phong cach bo cuc lam moi video (>= 40% visual refresh):
    # "letterbox" (Chuan dien anh 2.05:1 - vien am 6.6%), "ambient_frame" (Bo goc 92%),
    # "ken_burns" (Lia may cham), "light_leak" (Vet sang quang hoc), "none" (16:9 goc)
    visual_layout_mode: str = "letterbox"
    # Tuy chon bat/tat thu phong (Zoom 105% & Punch Zoom)
    add_zoom: bool = True
    # Tuy chon bat/tat dich cao do audio goc (+1.5% Pitch Shift)
    add_pitch_shift: bool = True
    # KT#12: Chay chu thuong hieu tren dai vien mo (Marquee Running Banner)
    marquee_enabled: bool = True
    marquee_text: str = "VIURECAP"
    marquee_direction: str = "right_to_left"  # "right_to_left" (Phai -> Trai) hoac "left_to_right" (Trai -> Phai)
    marquee_speed: int = 70  # toc do pixel / giay (mac dinh 70px/s: em ai, cham rai, sang trong)
    # KT#13: Nguy trang nhac nen (Music Camouflage) - pha nhan dien Content ID cho nhac nen
    # Dung aecho (vi echo ~9ms) + afreqshift (+3Hz) - FFmpeg native, khong anh huong toc do xuat.
    # Pham vi: thay doi timbre + delay profile nhac nen du de qua ACRCloud / YouTube Content ID
    # nhung nguoi nghe hoan toan khong phan biet duoc (nguong 10ms, 3Hz la vi mo).
    add_music_camouflage: bool = False  # mac dinh TAT vi chi can thiet khi video co nhac goc

    def to_dict(self) -> dict:
        return {
            "enabled": bool(self.enabled),
            "allow_horizontal_flip": bool(self.allow_horizontal_flip),
            "flip_mode": str(self.flip_mode),
            "flip_normal_seconds": int(self.flip_normal_seconds),
            "flip_duration_seconds": int(self.flip_duration_seconds),
            "add_zoom": bool(self.add_zoom),
            "zoom_percent": float(self.zoom_percent),
            "random_color_grade": bool(self.random_color_grade),
            "color_grading_mode": str(self.color_grading_mode),
            "color_cycle_seconds": int(self.color_cycle_seconds),
            "visual_layout_mode": str(self.visual_layout_mode),
            "geometric_mode": str(self.geometric_mode),
            "add_grain_noise": bool(self.add_grain_noise),
            "add_unsharp": bool(self.add_unsharp),
            "add_micro_speed": bool(self.add_micro_speed),
            "crop_offset_px": int(self.crop_offset_px),
            "add_pitch_shift": bool(self.add_pitch_shift),
            "pitch_shift_semitones": float(self.pitch_shift_semitones),
            "add_eq_audio": bool(self.add_eq_audio),
            "add_volume_level": bool(self.add_volume_level),
            "poison_metadata": bool(self.poison_metadata),
            "project_name": str(self.project_name),
            "continuous_mode": bool(self.continuous_mode),
            "skip_audio_filter": bool(self.skip_audio_filter),
            "marquee_enabled": bool(self.marquee_enabled),
            "marquee_text": str(self.marquee_text),
            "marquee_direction": str(self.marquee_direction),
            "marquee_speed": int(self.marquee_speed),
            "add_music_camouflage": bool(self.add_music_camouflage),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> AntiDuplicateSettings:
        if not data or not isinstance(data, dict):
            return cls()
        s = cls()
        for key, val in data.items():
            if hasattr(s, key):
                setattr(s, key, val)
        return s

    def summary_text(self) -> str:
        """Tra ve chuoi tom tat cac buoc dang bat/tat de hien thi tren UI."""
        if not self.enabled:
            return "Đang tắt"
        flip_m = getattr(self, "flip_mode", "periodic")
        color_m = getattr(self, "color_grading_mode", "periodic")
        layout_m = getattr(self, "visual_layout_mode", "letterbox")
        disabled = []
        if not getattr(self, "allow_horizontal_flip", True) or flip_m == "none":
            disabled.append("Tắt lật")
        elif flip_m == "always":
            disabled.append("Lật 100%")
        if not getattr(self, "add_zoom", True):
            disabled.append("Zoom")
        if not getattr(self, "random_color_grade", True) or color_m == "none":
            disabled.append("Chỉnh màu")
        elif color_m == "random":
            disabled.append("Màu cố định")
        if layout_m == "none":
            disabled.append("Bố cục 16:9")
        elif layout_m == "ambient_frame":
            disabled.append("Viền Ambient")
        elif layout_m == "ken_burns":
            disabled.append("Lia máy")
        elif layout_m == "light_leak":
            disabled.append("Vệt sáng")
        if not getattr(self, "marquee_enabled", True):
            disabled.append("Tắt chạy chữ")
        if getattr(self, "geometric_mode", "both") in ("none", "", None):
            disabled.append("Biến dạng")
        if not getattr(self, "add_grain_noise", True):
            disabled.append("Hạt noise")
        if not getattr(self, "add_unsharp", True):
            disabled.append("Tăng nét")
        if not getattr(self, "add_micro_speed", True):
            disabled.append("Vi tốc độ")
        if not getattr(self, "add_pitch_shift", True):
            disabled.append("Cao độ")
        if not getattr(self, "add_eq_audio", True):
            disabled.append("EQ")
        if not getattr(self, "add_volume_level", True):
            disabled.append("Volume")
        if not getattr(self, "poison_metadata", True):
            disabled.append("Metadata")
        # Hiển thị text marquee hiện tại để user kiểm tra
        marquee_txt = getattr(self, "marquee_text", "VIURECAP") or "VIURECAP"
        marquee_on = getattr(self, "marquee_enabled", True)
        marquee_info = f" · Chữ: \"{marquee_txt}\"" if marquee_on else ""
        if not disabled:
            return f"Xen kẽ 80% xuôi/20% lật · 4 tone màu · Mờ viền điện ảnh{marquee_info} (Tối ưu)"
        return f"Tùy chỉnh ({', '.join(disabled[:3])}{'...' if len(disabled) > 3 else ''}){marquee_info}"


def get_system_font_for_ffmpeg() -> str:
    """Tim font he thong thich hop cho bo loc drawtext cua FFmpeg tren Windows/Linux."""
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c.replace(":", "\\:")
    return ""


def build_marquee_text_filter(
    text: str = "VIURECAP",
    direction: str = "right_to_left",
    speed: int = 150,
    target_w: int = 1920,
    target_h: int = 1080,
) -> str:
    """Tao bo loc drawtext de chay chu thuong hieu o dai vien tren (vung duong vien top).
    
    direction: 'right_to_left' (Phai sang Trai) hoac 'left_to_right' (Trai sang Phai).
    speed: toc do cuon pixel moi giay (mac dinh 150px/s).
    """
    tw = int(target_w or 1920)
    th = int(target_h or 1080)
    bar_h = max(24, int(th * 0.0667))
    font_size = max(16, min(28, int(bar_h * 0.36)))
    y_pos = max(8, int((bar_h - font_size) / 2))
    
    clean_text = (text or "VIURECAP").strip()
    if not clean_text:
        clean_text = "VIURECAP"
    escaped_text = clean_text.replace("'", "'\\''").replace(":", "\\:")
    
    font_arg = ""
    font_file = get_system_font_for_ffmpeg()
    if font_file:
        font_arg = f"fontfile='{font_file}':"
    
    spd = max(30, min(600, int(speed or 70)))
    dir_mode = str(direction or "right_to_left").strip().lower()
    
    if dir_mode == "left_to_right":
        x_expr = f"-text_w+mod(t*{spd}\\,w+text_w)"
    else:
        # right_to_left
        x_expr = f"w-mod(t*{spd}\\,w+text_w)"
        
    return (
        f"drawtext={font_arg}text='{escaped_text}':fontsize={font_size}:"
        f"fontcolor=white@0.88:shadowcolor=black@0.65:shadowx=1:shadowy=1:"
        f"y={y_pos}:x='{x_expr}'"
    )


def build_visual_layout_filter(layout_mode: str, target_w: int = 1920, target_h: int = 1080) -> list[str]:
    """Sinh bo loc bien doi bo cuc lam moi video (>= 40% visual refresh).
    
    1. 'letterbox': Chuan dien anh 2.05:1 (Univisium - Mo nhe chuyen tiep, khong vien)
       - Mo nhe nhang (Soft Translucent Mist) 72px moi ben (~6.6% chieu cao), an toan tuyet doi cho tran & phu de.
       - Bo hoan toan cac duong vien mau vang/cam sac canh de hinh anh tu nhien, sang trong.
    2. 'ambient_frame': Bo goc noi khoi 92% + Vien Ambient Slate/Cyan
       - Thu nho 92% (1766x994), dem nen Slate #0f172a, vien chi Cyan 2px.
    3. 'ken_burns': Cu lia may gia lap (Dynamic Slow Pan & Micro Drift)
       - Zoom nhe 104%, lia may cham 0.3px/s theo chu ky hinh sin 60s -> 100% toa do lech theo thoi gian.
    4. 'light_leak': Vet sang quang hoc & Hat bui dien anh
       - Vignette quang hoc chuyen dong goc tren tao vet nang dien anh mo ao.
    5. 'none': Giu nguyen 16:9 goc.
    """
    mode = str(layout_mode or "none").strip().lower()
    tw = int(target_w or 1920)
    th = int(target_h or 1080)
    
    if mode == "letterbox":
        bar_h = max(24, int(th * 0.0667))
        h1 = int(bar_h * 0.70)
        h2 = int(bar_h * 0.18)
        h3 = bar_h - h1 - h2
        return [
            f"drawbox=y=0:w={tw}:h={h1}:color=black@0.30:t=fill",
            f"drawbox=y={h1}:w={tw}:h={h2}:color=black@0.18:t=fill",
            f"drawbox=y={h1+h2}:w={tw}:h={h3}:color=black@0.06:t=fill",
            f"drawbox=y={th-bar_h}:w={tw}:h={h3}:color=black@0.06:t=fill",
            f"drawbox=y={th-bar_h+h3}:w={tw}:h={h2}:color=black@0.18:t=fill",
            f"drawbox=y={th-bar_h+h3+h2}:w={tw}:h={h1}:color=black@0.30:t=fill",
        ]
    elif mode == "ambient_frame":
        sw = int(tw * 0.92) // 2 * 2
        sh = int(th * 0.92) // 2 * 2
        pad_x = (tw - sw) // 2
        pad_y = (th - sh) // 2
        return [
            f"scale={sw}:{sh}:flags=fast_bilinear",
            f"pad={tw}:{th}:{pad_x}:{pad_y}:color=0x0f172a",
            f"drawbox=x={pad_x-2}:y={pad_y-2}:w={sw+4}:h={sh+4}:color=0x38bdf8@0.70:t=2",
        ]
    elif mode == "ken_burns":
        PI = "3.14159265358979"
        cw = int(tw * 0.95) // 2 * 2
        ch = int(th * 0.95) // 2 * 2
        crop_x = f"(iw-ow)/2+((iw-ow)*0.45)*sin(2*{PI}*t/60)"
        crop_y = f"(ih-oh)/2+((ih-oh)*0.25)*cos(2*{PI}*t/60)"
        return [
            f"crop=w='{cw}':h='{ch}':x='{crop_x}':y='{crop_y}'",
            f"scale={tw}:{th}:flags=fast_bilinear",
        ]
    elif mode == "light_leak":
        PI = "3.14159265358979"
        return [
            f"vignette=angle='PI/5+PI/20*sin(2*{PI}*t/30)':x0='w*0.82':y0='h*0.18'",
            "eq=gamma_r=1.04:saturation=1.03",
        ]
    return []


def _daily_seed(offset=0):
    raw = datetime.now(timezone.utc).strftime("%Y%m%d").encode()
    return int(hashlib.md5(raw).hexdigest(), 16) % (2**32) + offset

def build_zoom_filter(zoom_percent):
    """KT#2a: Zoom video len roi crop ve cu, pha Visual Hash."""
    zoom = max(0.5, min(10.0, float(zoom_percent)))
    s = 1.0 + zoom / 100.0
    return "scale=iw*{:.4f}:ih*{:.4f},crop=iw/{:.4f}:ih/{:.4f}".format(s, s, s, s)

def build_periodic_color_grade_filters(interval_seconds: int = 240, total_duration: float = None) -> list[str]:
    """Đề xuất 1 (Nâng cấp độ sâu 10-12%): Xoay vòng 4 Tone màu điện ảnh đậm đà mỗi interval_seconds (mặc định 240s = 4 phút).
    Chu kỳ lặp 4 tone: 4 * interval_seconds = 960s (16 phút).
    - Tone 1: Warm Amber Glow (0-4m) - Vàng ấm rực rỡ, da hồng hào sáng bừng (R+10%, B-10%, Sat+8%, Cont+3%)
    - Tone 2: Moody Teal (4-8m) - Xanh lạnh sâu điện ảnh hiện đại (R-12%, B+12%, Sat+5%, Cont+4%)
    - Tone 3: Deep Contrast (8-12m) - Tương phản khối 3D cực sâu (Cont+8%, Sat+10%, Gamma-4%, Br-0.015)
    - Tone 4: Retro Matte (12-16m) - Màu phim nhựa hoài niệm cổ điển (Cont-5%, Gamma+5%, Sat-10%, Gamma_g+4%, Gamma_r+2%)
    
    Khi một tone không kích hoạt theo mốc thời gian t, eq filter tương ứng bypass (0 cost GPU/CPU).
    """
    s = max(10, int(interval_seconds or 240))
    if total_duration is not None and 0 < total_duration < s * 4:
        s = max(15, int(total_duration / 4))
    p = s * 4
    t1_end = s
    t2_end = s * 2
    t3_end = s * 3
    t4_end = p
    return [
        f"eq=gamma_r=1.10:gamma_b=0.90:saturation=1.08:contrast=1.03:enable='between(mod(t,{p}),0,{t1_end})'",
        f"eq=gamma_r=0.88:gamma_b=1.12:saturation=1.05:contrast=1.04:enable='between(mod(t,{p}),{t1_end},{t2_end})'",
        f"eq=contrast=1.08:brightness=-0.015:saturation=1.10:gamma=0.96:enable='between(mod(t,{p}),{t2_end},{t3_end})'",
        f"eq=contrast=0.95:gamma=1.05:saturation=0.90:gamma_g=1.04:gamma_r=1.02:enable='between(mod(t,{p}),{t3_end},{t4_end})'",
    ]

def build_random_color_grade_filter(rng):
    """KT#2b: Random color grade vi mo (Giai phap 1: brightness [-0.005, 0.005], contrast & gamma +-1%).
    
    Giu cho khung hinh co do tuong phan sau, trong veo, khong bi chay sang / bac mau.
    """
    br = rng.uniform(-0.005, 0.005)
    ct = rng.uniform(0.99, 1.01)
    sa = rng.uniform(0.98, 1.02)
    gm = rng.uniform(0.99, 1.01)
    return "eq=brightness={:.4f}:contrast={:.4f}:saturation={:.4f}:gamma={:.4f}".format(br, ct, sa, gm)

def build_geometric_distortion_filter(mode):
    """KT#4: Bien dang hinh hoc nhe - dich chuyen toa do pixel."""
    mode = str(mode or "both").strip().lower()
    parts = []
    if mode in ("crop", "both"):
        parts.append("crop=iw*0.965:ih*0.965:iw*0.02:ih*0.02,scale=trunc(iw/0.965/2)*2:trunc(ih/0.965/2)*2")
    if mode in ("vignette", "both"):
        parts.append("vignette=angle=PI/8")
    return ",".join(parts)


def build_anti_duplicate_video_chain(settings, target_w=None, target_h=None, total_duration=None):
    """Tra ve FFmpeg vf chain tong hop KT#2 + KT#4 + KT#6 + KT#7 + KT#8 + Auto Recap 12 Rules.

    KT#6: Grain noise nhe (noise=alls=8:allf=t+u) - pha perceptual hash DCT.
    KT#7: Micro speed variation (setpts=0.9999*PTS) - dich nhip thoi gian 0.01%.
    KT#8: Crop offset 3px - pha DCT block boundary.

    Tra ve chuoi rong neu settings.enabled=False.
    Them vao filter_complex TRUOC cac filter chinh (color, blur, ass).
    """
    if not settings.enabled:
        return ""
    parts = []

    dur = None
    if total_duration is not None:
        try:
            dur = float(total_duration)
        except (TypeError, ValueError):
            dur = None

    # 0. Phản chiếu (CapCut horizontal reflection):
    # - "none" hoac allow_horizontal_flip=False: khong lat (0%)
    # - "always": lat toan bo video (100%)
    # - "periodic" (Mac dinh Cach 2): 4 phut xuoi / 1 phut lat (Ti le 80% xuoi / 20% lat)
    allow_flip = getattr(settings, "allow_horizontal_flip", True)
    flip_mode = getattr(settings, "flip_mode", "periodic")
    if not allow_flip or flip_mode == "none":
        pass
    elif flip_mode == "always":
        parts.append("hflip")
    else:
        # Cach 2: Xen ke chu ky (mac dinh 4 phut xuoi / 1 phut lat = chu ky 300 giay)
        normal_s = int(getattr(settings, "flip_normal_seconds", 240) or 240)
        flip_s = int(getattr(settings, "flip_duration_seconds", 60) or 60)
        period = max(2, normal_s + flip_s)
        
        # Tu dong thich ung theo do dai video:
        # Neu video ngan hon 1 chu ky day du 300s (vi du video 2 phut = 124s cua nguoi dung):
        # Co gian chu ky xen ke (ti le 80% xuoi / 20% lat) de video ngan van co nhung nhip lat phan chieu ro rang
        if dur is not None and 0 < dur < period:
            cycle_s = max(20, min(60, int(dur / 2)))
            f_s = max(4, int(cycle_s * 0.20))
            n_s = cycle_s - f_s
            parts.append(f"hflip=enable='between(mod(t,{cycle_s}),{n_s},{cycle_s})'")
        else:
            parts.append(f"hflip=enable='between(mod(t,{period}),{normal_s},{period})'")

    # 1. Zoom & Crop: Neu la continuous mode (Auto Recap), dung chuan YouTube 16:9 crop 5% + punch zoom
    if getattr(settings, "continuous_mode", False):
        if getattr(settings, "add_zoom", True):
            PI = "3.14159265358979"
            tw = int(target_w or getattr(settings, "target_width", 1920) or 1920)
            th = int(target_h or getattr(settings, "target_height", 1080) or 1080)
            crop_w = int(tw * 0.95) // 2 * 2
            crop_h = int(th * 0.95) // 2 * 2
            punch_w = int(tw * 0.91) // 2 * 2
            punch_h = int(th * 0.91) // 2 * 2
            # KT#8: Dich offset crop khoi trung tam -> pha DCT block boundary
            # Dam bao offset an toan: max_safe_x = (iw - crop_w) / 2 - 1px
            # Vi du 1920px: (1920-1824)/2 = 48px -> offset 3px la an toan tuyet doi
            offset_px = int(getattr(settings, "crop_offset_px", 3))
            crop_expr_w = f"if(between(mod(t,45),18,22),{punch_w},{crop_w})"
            crop_expr_h = f"if(between(mod(t,45),18,22),{punch_h},{crop_h})"
            # x/y: dich 'offset_px' px khoi trung tam theo chieu duong (sang phai, xuong duoi)
            crop_expr_x = f"(iw-ow)/2+{offset_px}"
            crop_expr_y = f"(ih-oh)/2+{offset_px}"
            parts.append(
                f"crop=w='{crop_expr_w}':h='{crop_expr_h}':x='{crop_expr_x}':y='{crop_expr_y}',"
                f"scale={tw}:{th}:flags=fast_bilinear"
            )
            parts.append(f"hue=h='2*sin(2*{PI}*t/25)':s='1.0+0.02*sin(2*{PI}*t/20)'")
    else:
        if getattr(settings, "add_zoom", True) and settings.zoom_percent and settings.zoom_percent > 0.1:
            zoom_f = build_zoom_filter(settings.zoom_percent)
            if zoom_f:
                parts.append(zoom_f)

    # 2. Color grade (Đề xuất 1: Xoay vòng 4 tone màu điện ảnh mỗi 4 phút)
    if getattr(settings, "random_color_grade", True):
        color_mode = getattr(settings, "color_grading_mode", "periodic")
        if color_mode == "periodic":
            cycle_s = int(getattr(settings, "color_cycle_seconds", 240) or 240)
            parts.extend(build_periodic_color_grade_filters(cycle_s, total_duration=dur))
        elif color_mode != "none":
            seed = settings.color_seed if settings.color_seed is not None else _daily_seed()
            color_f = build_random_color_grade_filter(random.Random(seed))
            if color_f:
                parts.append(color_f)

    # 3. Geometric distortion (vignette, ...)
    if getattr(settings, "geometric_mode", "both") not in ("none", "", None):
        geo_f = build_geometric_distortion_filter(settings.geometric_mode)
        if geo_f:
            parts.append(geo_f)

    # 4. Bố cục làm mới video (Visual Refresh Layout >= 40%)
    layout_mode = getattr(settings, "visual_layout_mode", "letterbox")
    if layout_mode and layout_mode != "none":
        tw = int(target_w or getattr(settings, "target_width", 1920) or 1920)
        th = int(target_h or getattr(settings, "target_height", 1080) or 1080)
        layout_filters = build_visual_layout_filter(layout_mode, tw, th)
        if layout_filters:
            parts.extend(layout_filters)

    # 4b. Chạy chữ thương hiệu trên dải viền mờ (Marquee Running Text)
    if getattr(settings, "marquee_enabled", False):
        tw = int(target_w or getattr(settings, "target_width", 1920) or 1920)
        th = int(target_h or getattr(settings, "target_height", 1080) or 1080)
        _marquee_text_actual = getattr(settings, "marquee_text", "VIURECAP")
        print(f"[AntiDup] Marquee text being applied: '{_marquee_text_actual}' | dir={getattr(settings, 'marquee_direction', 'right_to_left')} | speed={getattr(settings, 'marquee_speed', 70)}")
        m_filter = build_marquee_text_filter(
            text=_marquee_text_actual,
            direction=getattr(settings, "marquee_direction", "right_to_left"),
            speed=getattr(settings, "marquee_speed", 70),
            target_w=tw,
            target_h=th,
        )
        if m_filter:
            parts.append(m_filter)

    if getattr(settings, "continuous_mode", False):
        parts.append("setsar=1")

        # KT#6: Grain noise cuc nho - pha perceptual hash DCT cua Content ID
        # alls=8: bien do 8/255 (~3%) - mat thuong khong phan biet duoc
        # allf=t+u: temporal + uniform noise (bien doi theo tung khung hinh)
        # Khong thay doi thoi luong video.
        if getattr(settings, "add_grain_noise", True):
            parts.append("noise=alls=8:allf=t+u")

        # KT#10: Unsharp nhe - pha perceptual hash pixel-level
        # luma_amount=0.5: tang nhe do sac net cua kenh sang (Y) -> thay doi edge gradient
        # chroma_amount=0: khong cham den mau (giu mau tu nhien)
        # Mat thuong: nhin "sac net" hon nho hon. AI Content ID: edge fingerprint khac hoan toan.
        # Khong thay doi thoi luong video.
        if getattr(settings, "add_unsharp", True):
            parts.append("unsharp=3:3:0.5:3:3:0")

        # KT#7: Micro speed variation - dich nhip thoi gian 0.01%
        # setpts=0.9999*PTS: video nhanh hon 0.01% -> thoi luong ngan hon 0.01%
        # Vi du: 120s (2 phut) -> 119.988s (ngan hon 0.012s = khong dang ke)
        # Audio se duoc bu tru tuong ung bang atempo=1.0001 trong audio filter
        # -> Video va audio van dong bo hoan hao, thoi luong cuoi cung nhu nhau.
        if getattr(settings, "add_micro_speed", True):
            parts.append("setpts=0.9999*PTS")


    return ",".join(f for f in parts if f)

def build_anti_duplicate_audio_filter(settings):
    """KT#5 + KT#9 + KT#7: Tra ve FFmpeg -af filter de pha audio fingerprint.

    KT#5: Dich pitch +1.5% bang asetrate + resample + atempo compensate.
    KT#9: Audio EQ nhe (equalizer filter) - pha audio fingerprint Chromaprint/Shazam.
          - 1200Hz +0.8dB: tang nhe dai trung (giong noi robusts)
          - 5500Hz -0.6dB: cat nhe dai cao (overtone)
          Nguoi nghe: khong phan biet duoc. AI quet: spectrum khac hoan toan.
    KT#7: Bu tru toc do 0.01% (atempo=1.0001) tuong ung voi setpts=0.9999*PTS tren video.
          Dam bao video va audio dong bo, thoi luong cuoi cung khong thay doi.

    Content ID / Shazam: spectrogram khac hoan toan -> khong match.
    Tra ve chuoi rong neu settings.enabled=False.
    """
    if not settings.enabled:
        return ""
    # Audio track da la TTS/dub: khong duoc bien dang pitch/EQ/volume.
    # Chi pha nhan dien VIDEO, con audio giu nguyen de nguoi nghe khong phan biet.
    if getattr(settings, "skip_audio_filter", False):
        return ""
    if getattr(settings, "continuous_mode", False):
        chain_parts = []
        if getattr(settings, "add_pitch_shift", True):
            pitch_rate = int(44100 * 1.015)       # 44761 Hz
            tempo_comp = round(1.0 / 1.015, 6)    # 0.985222
            chain_parts.append(f"aresample=44100,asetrate={pitch_rate},aresample=44100,atempo={tempo_comp}")

        # KT#9: EQ nhe - pha Chromaprint/Shazam audio fingerprint
        if getattr(settings, "add_eq_audio", True):
            chain_parts.append(
                "equalizer=f=1200:width_type=o:width=2:g=0.8"
                ",equalizer=f=5500:width_type=o:width=2:g=-0.6"
            )

        # KT#11: Volume -0.3dB (volume=0.97) - pha audio level fingerprint
        # Giam am luong 3% (tuong duong -0.26dB):
        # - Tai nguoi: khong the phan biet duoc (nguong nghe ~1dB)
        # - AI Shazam / ACRCloud: so sanh muc PCM -> level khac -> khong khop fingerprint
        # Khong thay doi thoi luong, khong thay doi pitch, khong thay doi nhip.
        if getattr(settings, "add_volume_level", True):
            chain_parts.append("volume=0.97")

        # KT#7: Bu tru micro speed (tuong ung setpts=0.9999*PTS tren video)
        # atempo=1.0001: audio nhanh hon 0.01% -> dong bo voi video da duoc setpts=0.9999
        # Thoi luong output = 99.99% thoi luong goc -> khong dang ke (0.012s voi video 2 phut)
        if getattr(settings, "add_micro_speed", True):
            chain_parts.append("atempo=1.0001")

        # KT#13: Nguy trang nhac nen (Music Camouflage) - chi khi bat tuong minh
        # Muc tieu: nhan dien nhac nen co ban quyen (YouTube Content ID / ACRCloud / Shazam)
        #   - aecho=0.6:0.88:9:0.3  -> Micro-echo 9ms, gain 0.3 (nguoi nghe: khong nghe ro)
        #     Thay doi delay profile cua nhac -> ACRCloud mat fingerprint match
        #   - afreqshift=shift=3.0  -> Dich tan so +3Hz (nguoi nghe: <0.1 cent, vo cam)
        #     Thay doi pitch reference cua Shazam, qua ACRCloud frequency fingerprint
        # Ket hop 2 filter: bao phu ca time-domain va frequency-domain fingerprint.
        # FFmpeg native: toc do xuat giu nguyen (chi them ~0.5% CPU nhe).
        if getattr(settings, "add_music_camouflage", False):
            chain_parts.append("aecho=0.6:0.88:9:0.3")
            chain_parts.append("afreqshift=shift=3.0")

        return ",".join(chain_parts)

    if getattr(settings, "add_pitch_shift", True) and settings.pitch_shift_semitones > 0:
        semitones = max(0.5, min(3.0, float(settings.pitch_shift_semitones or 2.0)))
        seed = settings.pitch_seed if settings.pitch_seed is not None else _daily_seed(1337)
        rng = random.Random(seed)
        direction = rng.choice([1, -1])
        shift_ratio = 1.0 + direction * semitones / 100.0
        atempo = max(0.5, min(2.0, 1.0 / shift_ratio))
        new_rate = int(44100 * shift_ratio)
        return "asetrate={},aresample=44100,atempo={:.6f}".format(new_rate, atempo)
    return ""

def get_metadata_poison_args(settings):
    """KT#3: Tra ve FFmpeg args de reset metadata file output.

    Them vao cuoi command truoc output_path:
        cmd = [..., *get_metadata_poison_args(settings), output_path]
    Tra ve list rong neu settings.enabled=False hoac poison_metadata=False.
    """
    if not settings.enabled or not settings.poison_metadata:
        return []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    name = str(settings.project_name or "VIUStudio").strip() or "VIUStudio"
    return [
        "-map_metadata", "-1",
        "-metadata", "encoder={}".format(name),
        "-metadata", "creation_time={}".format(now_iso),
        "-metadata", "comment=",
        "-metadata", "title=",
        "-metadata", "artist=",
        "-metadata", "copyright=",
    ]

def apply_anti_duplicate_to_command(command, settings, *, output_path, has_audio=True, has_existing_af=False):
    """Tien ich chen tat ca anti-duplicate args vao FFmpeg command truoc output_path.

    Args:
        command: FFmpeg command list (se duoc modify in-place).
        settings: AntiDuplicateSettings.
        output_path: Duong dan output (phai la command[-1]).
        has_audio: Co audio track khong.
        has_existing_af: Da co -af chua (de tranh duplicate).
    Returns:
        command da duoc modify (same object).
    """
    if not settings.enabled:
        return command
    if not command or str(command[-1]) != str(output_path):
        return command
    command.pop()
    meta_args = get_metadata_poison_args(settings)
    if meta_args:
        command.extend(meta_args)
    if has_audio and not has_existing_af:
        af_filter = build_anti_duplicate_audio_filter(settings)
        if af_filter:
            command.extend(["-af", af_filter])
    command.append(output_path)
    return command

def describe_settings(settings):
    """Tra ve chuoi mo ta ngan gon cau hinh dang dung."""
    if not settings.enabled:
        return "[AntiDuplicate] DISABLED"
    parts = ["[AntiDuplicate] ENABLED:"]
    zoom_pct = 100.0 + float(settings.zoom_percent or 0)
    if settings.zoom_percent > 0.1:
        parts.append("  Zoom {:.1f}%".format(zoom_pct))
    if settings.random_color_grade:
        parts.append("  RandomColorGrade")
    if settings.geometric_mode != "none":
        parts.append("  Geometric({})".format(settings.geometric_mode))
    if settings.pitch_shift_semitones > 0:
        parts.append("  PitchShift +/-{} semitones".format(settings.pitch_shift_semitones))
    if settings.poison_metadata:
        parts.append("  MetadataPoison")
    return "\n".join(parts)