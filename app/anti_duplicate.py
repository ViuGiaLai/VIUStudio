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
    # KT#8: Crop offset (px) - mac dinh 0px: co dinh 100% o chinh giua tam, khong nhay lech
    crop_offset_px: int = 0
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
    # Tuy chon bat/tat thu phong (Zoom 105% co dinh 100% chinh tam)
    add_zoom: bool = True
    # Tuy chon bat/tat dich cao do audio goc (+1.5% Pitch Shift)
    add_pitch_shift: bool = True
    # KT#12: Chay chu thuong hieu / Watermark mo dong (Bong nay 2D hoac Marquee)
    marquee_enabled: bool = True
    marquee_text: str = "VIURECAP"
    marquee_direction: str = "bouncing"  # "bouncing" (Bóng nảy 2D ngẫu nhiên), "right_to_left", "left_to_right"
    marquee_speed: int = 22  # toc do pixel / giay (mac dinh 22px/s: cuc cham, em ai)
    marquee_opacity: float = 0.40  # do mo ban trong suot mau trang khong vien (mac dinh 40%)
    # KT#15: Punch Zoom (Da loai bo khoi UI va mac dinh tat de dam bao khung hinh dung yen 100%)
    add_punch_zoom: bool = False
    punch_zoom_interval_seconds: float = 5.5  # Chu ky moi goc may (legacy)

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
            "marquee_opacity": float(self.marquee_opacity),
            "add_punch_zoom": bool(self.add_punch_zoom),
            "punch_zoom_interval_seconds": float(self.punch_zoom_interval_seconds),
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
        marquee_dir = getattr(self, "marquee_direction", "bouncing")
        dir_lbl = "Bóng nảy 2D" if marquee_dir == "bouncing" else ("L ➔ R" if marquee_dir == "left_to_right" else "R ➔ L")
        marquee_info = f" · Chữ ({dir_lbl}): \"{marquee_txt}\"" if marquee_on else ""
        if not disabled:
            return f"Xen kẽ 80% xuôi/20% lật · 4 tone màu{marquee_info} (Tối ưu)"
        return f"Tùy chỉnh ({', '.join(disabled[:3])}{'...' if len(disabled) > 3 else ''}){marquee_info}"


def escape_ffmpeg_filter_path(path: str) -> str:
    """Chuyen doi duong dan tep thanh dinh dang an toan cho bo loc FFmpeg tren moi he dieu hanh."""
    p = os.path.abspath(path).replace("\\", "/")
    return p.replace(":", "\\:").replace("'", "'\\''")


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
    direction: str = "bouncing",
    speed: int = 22,
    target_w: int = 1920,
    target_h: int = 1080,
    opacity: float = 0.40,
) -> str:
    """Tao bo loc drawtext chay chu thuong hieu / watermark mo ao.
    
    direction:
      - 'bouncing' (Mac dinh): Bong nay 2D cuc cham rai, ngau nhien khap man hinh video
        (Dung ty le vang phi ~ 0.618 de quy dao phu kin toan bo video, khong bao gio lap lai).
      - 'right_to_left': Chay ngang dai vien tren tu Phai sang Trai.
      - 'left_to_right': Chay ngang dai vien tren tu Trai sang Phai.
    speed: toc do pixel / giay (mac dinh 22px/s cho bouncing: cuc cham, em ai).
    opacity: do mo ban trong suot mau trang khong vien (mac dinh 0.40: trang sang, khong vien den).
    """
    tw = int(target_w or 1920)
    th = int(target_h or 1080)
    
    clean_text = (text or "VIURECAP").strip()
    if not clean_text:
        clean_text = "VIURECAP"
    escaped_text = clean_text.replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")
    
    font_arg = ""
    font_file = get_system_font_for_ffmpeg()
    if font_file:
        font_arg = f"fontfile='{font_file}':"
    
    dir_mode = str(direction or "bouncing").strip().lower()
    op = max(0.15, min(0.95, float(opacity or 0.40)))
    
    if dir_mode == "bouncing" or "bounce" in dir_mode or "ball" in dir_mode:
        # Font size ti le voi chieu cao video (chuan 1080p -> 30px, 720p -> 20px, 4K -> 60px)
        font_size = max(18, min(48, int(th * 0.028)))
        
        # Toc do cuc cham (mac dinh 22px/s)
        spd_x = max(8, min(200, int(speed or 22)))
        # Dung ty le vang phi ~ 0.618 de quy dao nay 2D khong bi trung lap chu ky
        spd_y = max(5, int(round(spd_x * 0.618)))
        
        # Le an toan (tranh sat mep va tranh de len vung phu de duoi day)
        pad_x = max(20, int(tw * 0.025))
        pad_y_top = max(25, int(th * 0.035))
        pad_y_bot = max(70, int(th * 0.12))  # Khoang trong cho subtitle ben duoi
        
        span_x_val = f"(w-text_w-{2 * pad_x})"
        span_y_val = f"(h-text_h-{pad_y_top + pad_y_bot})"
        
        # Thuat toan song tam giac (Triangle wave billiard bouncing)
        x_expr = f"{pad_x}+{span_x_val}-abs(mod(t*{spd_x}\\,2*{span_x_val})-{span_x_val})"
        y_expr = f"{pad_y_top}+{span_y_val}-abs(mod(t*{spd_y}\\,2*{span_y_val})-{span_y_val})"
        
        # Mau trang tinh khiet KHONG VIEN (Pure white, no border, no shadow)
        return (
            f"drawtext={font_arg}text='{escaped_text}':"
            f"fontsize={font_size}:fontcolor=white@{op:.2f}:"
            f"x='{x_expr}':y='{y_expr}'"
        )
    else:
        # Chay ngang dai vien tren (Legacy border banner)
        bar_h = max(20, int(round(th * 0.050)))
        font_size = max(14, min(24, int(bar_h * 0.38)))
        y_pos = max(6, int((bar_h - font_size) / 2))
        spd = max(30, min(600, int(speed or 70)))
        
        if dir_mode == "left_to_right":
            # Trai sang Phai: bat dau ngoai le trai (-text_w), chay sang phai (+text_w)
            x_expr = f"-text_w+mod(t*{spd}\\,w+text_w)"
        else:
            # Phai sang Trai (mac dinh): bat dau ngoai le phai (w), chay sang trai (-text_w)
            x_expr = f"w-mod(t*{spd}\\,w+text_w)"
            
        return (
            f"drawtext={font_arg}text='{escaped_text}':"
            f"fontsize={font_size}:fontcolor=white@0.85:"
            f"shadowcolor=black@0.60:shadowx=1:shadowy=1:"
            f"x='{x_expr}':y={y_pos}"
        )


def build_visual_layout_filter(layout_mode: str, target_w: int = 1920, target_h: int = 1080) -> list[str]:
    """Sinh bo loc bien doi bo cuc lam moi video (>= 40% visual refresh).
    
    1. 'letterbox': Dải đen điện ảnh mỏng 5% trên và dưới (Khuyên dùng)
       - Dải đen bán trong suốt black@0.75 độ cao 5.0% (54px ở 1080p) ở đỉnh và đáy video.
       - Vừa che khuyết điểm/chữ cũ mép viền, vừa tạo hiệu ứng chuẩn rạp phim sang trọng, giữ 90% diện tích video nguyên vẹn.
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
        bar_h = max(20, int(round(th * 0.050)))
        return [
            f"drawbox=y=0:w={tw}:h={bar_h}:color=black@0.75:t=fill",
            f"drawbox=y={th-bar_h}:w={tw}:h={bar_h}:color=black@0.75:t=fill",
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
        # This is a static vignette. Dithering every full-HD frame is costly
        # and brings no visible benefit at this deliberately subtle strength.
        parts.append("vignette=angle=PI/8:dither=0")
    return ",".join(parts)


def build_anti_duplicate_video_chain(settings, target_w=None, target_h=None, total_duration=None):
    """Tra ve FFmpeg vf chain tong hop KT#2 + KT#4 + KT#6 + KT#7 + KT#8 + Auto Recap 12 Rules.

    KT#6: Grain noise nhe (noise=alls=8:allf=t+u) - pha perceptual hash DCT.
    KT#7: Micro speed variation (setpts=0.9999*PTS) - dich nhip thoi gian 0.01%.
    KT#8: Crop offset 3px - pha DCT block boundary.

    Tra ve chuoi rong neu settings.enabled=False.
    Them vao filter_complex SAU cac filter che/blur/mau goc (color, blur, mask)
    de lop che di chuyen dong bo 100% voi video khi zoom/lat, va TRUOC phu de moi (ass).
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

    # 1. Zoom & Crop: Neu la continuous mode (Auto Recap), dung chuan YouTube 16:9 crop 5% co dinh 100% chinh tam
    if getattr(settings, "continuous_mode", False):
        if getattr(settings, "add_zoom", True):
            PI = "3.14159265358979"
            tw = int(target_w or getattr(settings, "target_width", 1920) or 1920)
            th = int(target_h or getattr(settings, "target_height", 1080) or 1080)
            offset_px = int(getattr(settings, "crop_offset_px", 0) or 0)
            crop_expr_x = f"(iw-ow)/2+{offset_px}" if offset_px else "(iw-ow)/2"
            crop_expr_y = f"(ih-oh)/2+{offset_px}" if offset_px else "(ih-oh)/2"

            if getattr(settings, "add_punch_zoom", False):
                iv = float(getattr(settings, "punch_zoom_interval_seconds", 5.5) or 5.5)
                period = round(iv * 2, 2)
                crop_expr_w = f"trunc(if(between(mod(t,{period}),{iv},{period}),iw*0.90,iw*0.95)/2)*2"
                crop_expr_h = f"trunc(if(between(mod(t,{period}),{iv},{period}),ih*0.90,ih*0.95)/2)*2"
                parts.append(
                    f"crop=w='{crop_expr_w}':h='{crop_expr_h}':x='{crop_expr_x}':y='{crop_expr_y}',"
                    f"scale={tw}:{th}:flags=fast_bilinear"
                )
            else:
                crop_expr_w = "trunc(iw*0.95/2)*2"
                crop_expr_h = "trunc(ih*0.95/2)*2"
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
    geo_mode = getattr(settings, "geometric_mode", "both")
    if geo_mode not in ("none", "", None):
        # Continuous Zoom/Punch Zoom above already crops 5-10% and scales back
        # to the target canvas.  Applying the legacy 3.5% geometric crop after
        # it performs a second full-HD scale, which is visually redundant and
        # was the largest CPU bottleneck in export.  Preserve the vignette part
        # of "both"; when Zoom is disabled, keep the requested crop unchanged.
        if getattr(settings, "continuous_mode", False) and getattr(settings, "add_zoom", True):
            if geo_mode == "both":
                geo_mode = "vignette"
            elif geo_mode == "crop":
                geo_mode = "none"
        geo_f = build_geometric_distortion_filter(geo_mode)
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

    # 4b. Chạy chữ thương hiệu / Watermark mờ động (Bóng nảy 2D hoặc viền mờ)
    if getattr(settings, "marquee_enabled", False):
        tw = int(target_w or getattr(settings, "target_width", 1920) or 1920)
        th = int(target_h or getattr(settings, "target_height", 1080) or 1080)
        _marquee_text_actual = getattr(settings, "marquee_text", "VIURECAP")
        _marquee_dir = getattr(settings, "marquee_direction", "bouncing")
        _marquee_spd = getattr(settings, "marquee_speed", 22)
        _marquee_op = getattr(settings, "marquee_opacity", 0.40)
        print(f"[AntiDup] Marquee text being applied: '{_marquee_text_actual}' | dir={_marquee_dir} | speed={_marquee_spd} | opacity={_marquee_op}")
        m_filter = build_marquee_text_filter(
            text=_marquee_text_actual,
            direction=_marquee_dir,
            speed=_marquee_spd,
            target_w=tw,
            target_h=th,
            opacity=_marquee_op,
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

        # KT#10: Contrast-adaptive sharpen nhe - pha perceptual hash pixel-level.
        # CAS supports slice threading and is substantially faster than the
        # old full-frame unsharp convolution while keeping chroma untouched.
        # Mat thuong: nhin "sac net" hon nho hon. AI Content ID: edge fingerprint khac hoan toan.
        # Khong thay doi thoi luong video.
        if getattr(settings, "add_unsharp", True):
            parts.append("cas=strength=0.15:planes=1")

        # KT#7: Micro speed variation - dich nhip thoi gian 0.01%
        # setpts=0.9999*PTS: video nhanh hon 0.01% -> thoi luong ngan hon 0.01%
        # Vi du: 120s (2 phut) -> 119.988s (ngan hon 0.012s = khong dang ke)
        # Audio se duoc bu tru tuong ung bang atempo=1.0001 trong audio filter
        # -> Video va audio van dong bo hoan hao, thoi luong cuoi cung nhu nhau.
        if getattr(settings, "add_micro_speed", True):
            parts.append("setpts=0.9999*PTS")


    return ",".join(f for f in parts if f)

def build_anti_duplicate_audio_filter(settings, *, include_bgm_overlay=False, **kwargs):
    """KT#5 + KT#9 + KT#11 + KT#7: Trả về FFmpeg -af filter để phá audio fingerprint.

    KT#5: Dịch pitch vi mô +1.5% bằng asetrate + resample + atempo compensate.
    KT#9: Audio EQ nhẹ (1200Hz +0.8dB, 5500Hz -0.6dB) - phá Chromaprint / Shazam.
    KT#11: Giảm âm lượng 3% (volume=0.97 / -0.26dB) - phá audio level fingerprint.
    KT#7: Bù trừ vi tốc độ 0.01% (atempo=1.0001) tương ứng với setpts=0.9999*PTS trên video.

    Người xem / nghe phim hoàn toàn tự nhiên, không chát tai, giữ nguyên chất phim điện ảnh.
    Trả về chuỗi rỗng nếu settings.enabled=False hoặc skip_audio_filter=True.
    """
    if not settings.enabled:
        return ""
    # Audio track đã là TTS/dub: không được biến dạng pitch/EQ/volume.
    # Chỉ phá nhận diện VIDEO, còn audio giữ nguyên để người nghe không phân biệt.
    if getattr(settings, "skip_audio_filter", False):
        return ""
    if getattr(settings, "continuous_mode", False):
        chain_parts = []
        if getattr(settings, "add_pitch_shift", True):
            pitch_rate = int(44100 * 1.015)       # 44761 Hz
            tempo_comp = round(1.0 / 1.015, 6)    # 0.985222
            chain_parts.append(f"aresample=44100,asetrate={pitch_rate},aresample=44100,atempo={tempo_comp}")

        # KT#9: EQ nhẹ - phá Chromaprint/Shazam audio fingerprint
        if getattr(settings, "add_eq_audio", True):
            chain_parts.append(
                "equalizer=f=1200:width_type=o:width=2:g=0.8"
                ",equalizer=f=5500:width_type=o:width=2:g=-0.6"
            )

        # KT#11: Volume -0.3dB (volume=0.97) - phá audio level fingerprint
        if getattr(settings, "add_volume_level", True):
            chain_parts.append("volume=0.97")

        # KT#7: Bù trừ micro speed (tương ứng setpts=0.9999*PTS trên video)
        if getattr(settings, "add_micro_speed", True):
            chain_parts.append("atempo=1.0001")

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

def apply_anti_duplicate_to_command(
    command,
    settings,
    *,
    output_path,
    has_audio=True,
    has_existing_af=False,
    audio_input_label="0:a",
    audio_map_value="0:a?",
):
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
    if has_audio:
        # Preserve any audio processing already authored by the export path
        # (for example Audio Mix gain) and merge it with Anti-Duplicate audio
        # settings. Previously ``has_existing_af=True`` skipped Pitch/EQ/BGM
        # altogether, so the custom dialog and final export could disagree.
        existing_audio_filters = []
        idx = 0
        while idx < len(command) - 1:
            if command[idx] == "-af":
                existing_audio_filters.append(str(command[idx + 1]))
                del command[idx:idx + 2]
                continue
            idx += 1

        af_filter = build_anti_duplicate_audio_filter(settings)
        main_audio_filter = ",".join(
            part for part in [*existing_audio_filters, af_filter] if part
        )
        if main_audio_filter:
            command.extend(["-af", main_audio_filter])
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
