# VIUStudio Web — Đặc tả giao diện và trải nghiệm người dùng

Phiên bản: 1.0  
Ngày: 07/09/2026  
Trạng thái: Đề xuất sản phẩm và tiêu chí triển khai; chưa phải tính năng web đã xây dựng.  
Định hướng đã chọn: Web đa người dùng + Local Worker xử lý trên máy từng người.  
Ngôn ngữ tài liệu: Tiếng Việt. Ngôn ngữ giao diện sản phẩm: English.

## 1. Mục tiêu và phạm vi

Xây dựng website để người dùng quản lý dự án và sử dụng công cụ SRT, TTS, nhận dạng lời nói, tách nhạc/giọng và xuất video từ một giao diện thống nhất. Các tác vụ nặng chạy bằng ứng dụng VIUStudio Worker trên máy người dùng. Website phục vụ điều hướng, tài khoản, metadata dự án và trạng thái tác vụ.

Người dùng phổ thông không cần nhập URL API, cổng kết nối hoặc lệnh Python. Họ cài Worker một lần, kết nối tài khoản, chọn file và thao tác trên web. Trong sản phẩm, tên hiển thị là `VIUStudio Companion`; thuật ngữ Local Worker dành cho tài liệu kỹ thuật.

Mục tiêu chi phí là giảm tối đa tiền thuê xử lý và lưu trữ media. Không cam kết dịch vụ miễn phí vô hạn: dịch vụ web có hạn mức; người dùng vẫn sử dụng điện, mạng, dung lượng và CPU/GPU của mình. Tác vụ qua nhà cung cấp AI bên ngoài có thể có chi phí riêng và cần được ghi rõ trước khi chạy.

Phạm vi tài liệu bao gồm giao diện công khai, đăng nhập, onboarding, quản lý dự án, bộ công cụ nhỏ, editor, thiết bị, tài nguyên, tiến độ, kết quả, cài đặt, quản trị và tiêu chí nghiệm thu. Live collaboration, lưu toàn bộ video lên cloud và render GPU trên máy chủ chưa nằm trong bản đầu.

## 2. Cơ sở từ dự án hiện tại

Các file đã khảo sát để lập tài liệu:

| Thành phần hiện tại | Vai trò | Hướng sử dụng cho web |
| --- | --- | --- |
| `app/services/workflow_runtime.py` | Gọi Prepare, Voice, Export và truyền cấu hình | Tái sử dụng qua adapter tác vụ |
| `app/remote_api_server.py` | API transcribe, translate, rewrite, TTS, prepare, voice, export | Bổ sung lớp job, thiết bị và giao thức; không coi là backend đa người dùng hoàn chỉnh |
| `app/services/voice_catalog_service.py` | Hợp nhất catalog giọng và kiểm tra một số model local | Là cơ sở cho catalog theo thiết bị, cần mở rộng thông tin capability |
| `ui/views/resource_manager.py` | Quản lý tài nguyên desktop | Tham chiếu nghiệp vụ cài, kiểm tra và gỡ model |
| `ui/features/timeline_editing.py` và `multi_video_timeline.py` | Thao tác timeline và nguồn video | Đối chiếu hành vi để web không tự tạo logic khác |
| `docs/ui-redesign-spec.md` | Định hướng UI desktop | Kế thừa ưu tiên Preview, Timeline, Inspector và task panel |

API hiện tại có `_STATUS` dùng chung và một số thao tác trả kết quả sau khi xử lý xong. Web cần trạng thái theo `job_id`, khả năng nhận lại kết quả sau reconnect và định danh chủ sở hữu. Không đưa trực tiếp API local hiện tại ra Internet như một dịch vụ cho tất cả tài khoản.

Catalog hiện khảo sát có các provider Piper, Edge, ZeroTTS và Kokoro. Điều này không chứng minh mọi engine đều sẵn sàng trên mọi máy. Giao diện phải dựa vào kiểm tra runtime, model và khả năng ngôn ngữ của thiết bị đã kết nối.

## 3. Phân chia web, cloud và máy người dùng

| Chức năng | Nơi thực hiện | Dữ liệu lưu mặc định |
| --- | --- | --- |
| Website, điều hướng | Trình duyệt | Cache giao diện |
| Đăng nhập, danh sách thiết bị | Cloud API | ID, tên, quyền, phiên đăng nhập |
| Danh sách dự án, trạng thái | Cloud API/database | Metadata, revision, trạng thái cuối đã xác nhận |
| Chỉnh và xuất SRT từ văn bản có sẵn | Trình duyệt | Bản nháp local; bản đồng bộ khi người dùng bật |
| Nhận dạng lời nói từ video/audio | Companion | Media, model, transcript |
| TTS bằng model local | Companion | Model và WAV |
| Tách Voice/Music | Companion | Audio nguồn và stem kết quả |
| Render video, tạo proxy | Companion | File tạm và output |
| Dịch bằng API bên ngoài | Qua provider người dùng chọn | Theo cấu hình provider; UI thông báo văn bản được gửi đi |

Không mặc định upload video/audio, đường dẫn tuyệt đối, API key hoặc file model lên cloud. Transcript cũng là nội dung riêng tư: `Sync subtitle text across devices` là lựa chọn riêng, mặc định tắt. Nếu tắt, thiết bị khác chỉ thấy metadata và trạng thái; không được hứa có thể sửa toàn bộ nội dung từ mọi máy.

Cloud đồng bộ quản lý dự án không đồng nghĩa cloud sao lưu media. Luôn có nhãn `Stored on this device`, `Metadata synced` hoặc `Subtitle text synced` phù hợp.

## 4. Kiến trúc thông tin

### 4.1 Website công khai

- `/`: giới thiệu sản phẩm, các công cụ và cách xử lý local.
- `/tools`: danh sách công cụ và yêu cầu của từng công cụ.
- `/download`: tải Companion, phiên bản và hệ điều hành được hỗ trợ.
- `/help`: hướng dẫn kết nối, model, lỗi thường gặp.
- `/sign-in`: đăng nhập.

Trang chủ có tiêu đề `Your media tools. Powered by your computer.` và CTA `Open Workspace`, `Download Companion`. Dưới CTA có ba bước: `Install Companion → Connect device → Start creating`.

Thẻ công cụ ghi rõ `Runs in browser` hoặc `Requires Companion`. Không ghi “Free unlimited AI” hoặc tạo cảm giác website cung cấp GPU miễn phí.

### 4.2 Không gian người dùng

| Điều hướng | Nội dung | Route đề xuất |
| --- | --- | --- |
| Overview | Tác vụ đang chạy, dự án gần đây, công cụ nhanh | `/app` |
| Projects | Danh sách và quản lý dự án | `/app/projects` |
| Tools | SRT, Transcript, TTS, Voice/Music | `/app/tools` |
| Tasks | Hàng đợi và lịch sử | `/app/tasks` |
| Devices | Kết nối, đổi tên, ngắt thiết bị | `/app/devices` |
| Resources | Model trên thiết bị đang chọn | `/app/resources` |
| Settings | Hồ sơ, đồng bộ, mặc định, dữ liệu | `/app/settings` |
| Help | Hướng dẫn và chẩn đoán | `/app/help` |

Editor có route `/app/projects/:projectId/editor`. Màn hình kết quả tác vụ có route `/app/tasks/:jobId`. Route chứa ID, không chứa tên file hay đường dẫn local.

## 5. Bố cục và phong cách giao diện

### 5.1 App shell

Desktop dùng sidebar khoảng 224 px, top bar khoảng 60 px, nội dung có khoảng đệm 24 px. Sidebar thu về icon khi thiếu chiều ngang. Editor được phép dùng hết chiều rộng, các trang quản lý giới hạn khoảng 1440 px để bảng dễ đọc.

Top bar gồm breadcrumb, tìm kiếm dự án, bộ chọn thiết bị, thông báo và avatar. Bộ chọn thiết bị luôn hiện tên máy và trạng thái: `My PC · Ready`, `My PC · Busy`, `My PC · Offline`.

```text
┌──────────────┬───────────────────────────────────────────────────┐
│ VIUStudio    │ Projects / My video        My PC · Ready   Avatar │
├──────────────┼───────────────────────────────────────────────────┤
│ Overview     │ Page title                         Primary action │
│ Projects     │ Supporting description                            │
│ Tools        │                                                   │
│ Tasks        │ Main content                                      │
│ Devices      │                                                   │
│ Resources    │                                                   │
│              │                                                   │
│ Settings     ├───────────────────────────────────────────────────┤
│ Help         │ TTS · 389/954 · 40.8%                View details  │
└──────────────┴───────────────────────────────────────────────────┘
```

### 5.2 Design tokens đề xuất

| Token | Giá trị định hướng |
| --- | --- |
| Page background | `#0B1020` |
| Surface | `#121A2B` |
| Raised surface | `#192338` |
| Border | `#2B3850` |
| Primary text | `#F1F5F9` |
| Secondary text | `#A8B6CC` |
| Brand accent | `#14B8A6` |
| Selection/focus | `#818CF8` |
| Success / Warning / Error | `#34D399` / `#FBBF24` / `#F87171` |
| Spacing | 4, 8, 12, 16, 24, 32 px |
| Corner radius | Input 8 px; card/dialog 12 px |
| Font | Inter, có fallback system font hỗ trợ dấu tiếng Việt và chữ CJK |

Đây là điểm bắt đầu cho thiết kế, cần đo tương phản trên từng cặp foreground/background. Nút nền teal dùng chữ tối nếu cần tương phản tốt. Không dùng chỉ màu để phân biệt lỗi, chọn hoặc đang chạy: luôn có nhãn/icon.

Body 14–16 px; tiêu đề trang 24–28 px; thời gian, số lượng và phần trăm dùng tabular numbers. Tránh quá nhiều card lồng nhau, gradient mạnh hoặc animation lặp trong màn hình làm việc.

### 5.3 Responsive và khả năng truy cập

- Từ 1280 px: sidebar và editor đầy đủ, inspector rộng khoảng 300–360 px.
- 768–1279 px: sidebar thu gọn, inspector mở thành panel, cho phép kéo splitter.
- Dưới 768 px: ưu tiên Projects, Tasks, metadata và chỉnh SRT cơ bản; không thu nhỏ timeline desktop đến mức khó dùng.
- Mobile không có Companion được hỗ trợ thì thông báo rõ; không hiển thị nút cài Windows như một hành động chạy được trên điện thoại.
- Điều khiển tối thiểu 40 px chiều cao, mục tiêu 44 px với thao tác cảm ứng.
- Toàn bộ form có label, lỗi liên kết với input, dialog giữ focus và trả focus khi đóng.
- Toast không là nơi duy nhất hiển thị lỗi. Screen reader chỉ nhận thông báo tiến độ theo nhịp hợp lý, không đọc mỗi event.
- Tôn trọng `prefers-reduced-motion`; hỗ trợ zoom trình duyệt 200% cho màn hình quản lý.

## 6. Đăng nhập và lần sử dụng đầu

### 6.1 Sign in

Đề xuất ưu tiên `Continue with Google` ở bản đầu. Đăng nhập email/mật khẩu hoặc magic link chỉ bổ sung khi đã có quy trình xác minh, khôi phục và gửi email hoạt động. Không trình bày nút email chưa có backend.

Trang đăng nhập có lỗi inline, trạng thái đang xác thực, nút thử lại và trở về trang đang mở sau khi thành công. Hết phiên đăng nhập phải giữ bản nháp, không xóa nội dung đang sửa.

### 6.2 Onboarding

1. `Welcome`: tên hiển thị, mô tả xử lý local và tùy chọn đồng bộ nội dung.
2. `Connect your computer`: tải Companion hoặc mở bản đã cài.
3. `Confirm pairing`: xác nhận mã và tài khoản trên Companion.
4. `Choose your tools`: Transcript, TTS, Separation; đề xuất chỉ tài nguyên cần thiết.
5. `Ready`: chọn `Create project` hoặc `Try SRT Editor`.

Cho phép `Set up later` để dùng quản lý và chỉnh SRT. Thiếu model TTS không được chặn đăng nhập hoặc mở dự án.

### 6.3 Ghép nối Companion

Web tạo yêu cầu ghép nối ngắn hạn, hiển thị mã và thời hạn. Người dùng mở Companion bằng nút hoặc nhập mã trong Companion. Companion hiển thị đúng tài khoản, tên thiết bị và phạm vi truy cập trước khi xác nhận.

Sau xác nhận, web chỉ báo `Connected` khi nhận handshake và capability của thiết bị. Mã đã dùng/hết hạn không dùng lại. Hỗ trợ `Create new code`, `Copy code`, `Open Companion`, `Troubleshoot connection`.

Không yêu cầu người dùng chép token vào URL. Không đưa token dài hạn vào clipboard hoặc localStorage của trang web. Tên thiết bị có thể sửa nhưng `device_id` giữ nguyên.

## 7. Overview

Màn hình mở đầu tập trung vào việc tiếp tục công việc:

- Hàng đầu: thiết bị đang chọn, tình trạng Companion và CTA phù hợp.
- `Active tasks`: tối đa ba tác vụ, có trạng thái thật và liên kết Tasks.
- `Recent projects`: sáu dự án gần nhất, nút `View all`.
- `Quick tools`: `SRT Editor`, `Original Transcript`, `Text to Speech`, `Voice / Music Separation`.
- `Needs attention`: model thiếu, file mất liên kết, revision conflict; ẩn hoàn toàn nếu không có.

Tài khoản mới hiển thị minh họa đơn giản và `Create your first project`. Số tác vụ đang chạy bằng 0 không phải lỗi. Không đưa số liệu giả hoặc biểu đồ usage không phục vụ hành động.

## 8. Projects và tạo dự án

### 8.1 Danh sách

Chế độ list/grid lưu theo người dùng. Mỗi dự án gồm tên, thời lượng nếu biết, source/target language, thiết bị chứa media, trạng thái workflow, thời gian chỉnh gần nhất và tình trạng đồng bộ.

Tìm kiếm theo tên; lọc thiết bị, trạng thái, archived; sắp xếp updated/name/created. Menu gồm `Open`, `Rename`, `Duplicate project`, `Archive`, `Delete`. Duplicate mặc định sao chép cấu hình và tham chiếu media; không âm thầm nhân đôi video lớn.

Thumbnail lấy từ file local chỉ khi có quyền và kết nối. Nếu chưa có thumbnail, dùng placeholder; không hiển thị `Empty project` chỉ vì chưa tải được ảnh.

### 8.2 Create project

Các trường: Project name, Processing device, Source files, Source language (`Auto detect`), Target language, Output goal. Mục tiêu gồm Transcript only, Translated subtitles, Subtitles + voice, Voice only.

`Choose files` mở picker local khi luồng kết nối hỗ trợ. File được cấp `asset_id`; trình duyệt không thể tự đọc một đường dẫn Windows chỉ từ chuỗi ký tự. Drop file vào web phải tạo phiên import về Companion có tiến độ nếu cần truyền; nhãn là `Importing to your device`, không gọi là upload cloud.

Chọn nhiều video phải hiện thứ tự, thời lượng và thao tác move/remove trước khi tạo. Kiểm tra thiếu file, định dạng chưa hỗ trợ và dung lượng. Tạo dự án xong chưa tự chạy toàn bộ pipeline: người dùng chọn bước trong editor.

### 8.3 Mở dự án trên máy khác

Hiện `Media is stored on another device`. Cho phép xem metadata và subtitle đã đồng bộ. Để xử lý phải chọn một thiết bị có file, hoặc `Relink media` trên máy mới. Không tự chuyển tác vụ sang máy online bất kỳ.

## 9. Tools — Công cụ dùng nhanh

Mỗi tool có cùng mẫu: Input → Options → Primary action → Progress → Results. Cho phép `Save as project`. Tool có worker vẫn tạo job ID để lịch sử và phục hồi hoạt động đúng.

### 9.1 SRT Editor

Nhận `.srt`, văn bản paste và import bản dịch. Hiện bảng cue với thời gian, nguyên bản, bản dịch, ký tự/giây và lỗi. Có tìm kiếm, thay thế, split/merge, undo/redo, chọn ngôn ngữ văn bản và export SRT UTF-8.

SRT nhập không có ID thì tạo ID ổn định ở lần import đầu. Cue có thời gian âm, end trước start hoặc overlap được đánh dấu; không tự “sửa tất cả” làm lệch timing. SRT download từ trình duyệt không cần Companion.

### 9.2 Original Transcript

Input video/audio, engine phù hợp từ capability, source language Auto/explicit. OCR là lựa chọn riêng khi nhận dạng phụ đề trên hình; cho phép chọn vùng OCR. Hiện thời lượng, thiết bị và tài nguyên cần trước khi chạy.

Kết quả là transcript nguyên ngữ và SRT, không âm thầm tạo bản dịch. Người dùng có thể `Edit transcript`, `Export SRT`, `Translate next`. Nếu video nguồn đã có chữ Việt được burn-in, giải thích đó là hình ảnh nguồn và thao tác clear transcript không loại bỏ được.

### 9.3 Text to Speech

Input văn bản, output language, engine, voice, speed và định dạng output được runtime hỗ trợ. `Preview voice` chỉ chạy khi người dùng bấm; chọn giọng không tự phát hoặc tạo toàn bộ audio.

Hiện giới hạn input theo capability thực tế. Văn bản dài được chia nội bộ nhưng phải ghép đầy đủ. Kết quả có play/pause, thời lượng, `Save audio`, `Open folder`, `Create subtitle project` nếu có timestamp khả dụng; không tự phát minh word timing.

### 9.4 Voice / Music Separation

Ba lựa chọn có nhãn English:

- `Keep music, remove voice`.
- `Keep voice, remove music`.
- `Create both Voice.wav and Music.wav`.

Trước khi chạy, kiểm tra model, runtime, dung lượng và nguồn audio. Thiếu model hiển thị `Install required model` ngay tại tool. Không hiện Ready khi cả hai stem vẫn trỏ tới extracted audio nguồn.

Kết quả có hai hàng riêng: Voice.wav và Music.wav, mỗi hàng có play, duration, size, Save, `Add to timeline`. Hai slider `Voice volume`, `Music volume` dùng để nghe mix thử; khi thêm timeline phải lưu gain tương ứng rõ ràng. Chỉ thêm stem đã tạo và kiểm tra thành công.

Nếu đã có một stem trên timeline, báo `Already added` và cho chọn thay thế/thêm bản sao rõ ràng. Có ghi chú ngắn: chất lượng tách phụ thuộc bản thu và model; có thể còn tiếng lọt hoặc mất một phần nhạc.

## 10. Editor workspace

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Projects / My video   Saved locally · Synced   Generate ▾   Export   │
├──────────┬───────────────────────────────────┬───────────────────────┤
│ Edit     │                                   │ Selected cue          │
│ Captions │          Video preview            │ Original text         │
│ Voice    │                                   │ Translated text       │
│ Audio    │                                   │ Start / End / Speaker │
│ Style    ├───────────────────────────────────┤ Voice / Timing        │
│ Media    │ Play  00:45.436 / 10:32.900   1×   │                       │
├──────────┴───────────────────────────────────┴───────────────────────┤
│ Timeline controls                  Zoom                 Fit timeline│
│ V1 Video        [clip 1] [clip 2]                                    │
│ Original Audio  [waveform]                                           │
│ Dub             [voice clips]                                       │
│ Music           [music stem]                                        │
│ Subtitles       [cue] [cue] [cue]                                    │
├──────────────────────────────────────────────────────────────────────┤
│ Export · Encoding 02:18 / 10:32 · 21.8%                 View details │
└──────────────────────────────────────────────────────────────────────┘
```

Tên track trong hình là tên chức năng; ánh xạ track ID theo model dữ liệu thực tế, không hard-code A2 luôn là Dub khi dự án đã dùng A2 cho Music.

### 10.1 Preview

Hiện chế độ `Source preview` hoặc `Rendered preview`. Nếu browser preview chưa hỗ trợ filter/ASS đầy đủ, badge phải nói rõ và có `Render preview` trên Companion. Không hiển thị preview nguồn như thể đó là output chính xác.

File không phát được trong browser có CTA `Create compatible preview`; Companion tạo proxy. Timebase editor dùng thời gian media, không nhân/chia theo playback speed. Phát 1.5× không được làm cue/export lệch.

Chọn cue chỉ thay selection/inspector. Seek là thao tác riêng bằng double-click hoặc `Jump to cue`. Chọn/right-click không thay audio source, mute, volume, cache TTS hay trạng thái phát. Inspector có nhãn `Selected cue`; cue đang phát được đánh dấu riêng để tránh hiểu nhầm hai thời gian.

### 10.2 Captions

Hai trường độc lập: `Original transcript` và `Translation`. Khi chưa dịch, trường Translation trống với placeholder, không chép nguyên bản vào rồi gắn nhãn “translated”. Preview có lựa chọn Original/Translation/Hidden.

Mỗi cue có `cue_id`, start, end, source text, translated text, speaker, voice assignment và trạng thái audio. Trạng thái audio gồm Missing, Generating, Ready, Outdated, Failed.

Sửa text cue A chỉ làm audio của A outdated. Sửa style không làm mất voice. Sửa timing có thể làm mix cần dựng lại nhưng không phải luôn cần tổng hợp lại WAV. Thay voice toàn dự án phải hiện số cue bị ảnh hưởng trước khi chạy.

Cảnh báo đọc quá dài sử dụng text rate để gợi ý, sau TTS dùng thời lượng audio thật để kiểm tra. Các lựa chọn gồm shorten text, adjust speed trong giới hạn, hoặc review timing. Không cắt phần cuối câu chỉ vì cue kế tiếp bắt đầu; không tự đẩy cả timeline lệch nguồn.

### 10.3 Dịch bên ngoài và import lại

`Export for translation` xuất SRT và định dạng có ID như JSON/XLSX khi hỗ trợ. Định dạng round-trip ưu tiên có project ID, revision, cue ID, start/end, source, translation. SRT dùng để tương thích, không có ID ổn định mặc định.

`Copy AI prompt` yêu cầu giữ ID, không đổi thời gian, không thêm/bỏ cue, giữ tên riêng nhất quán. Copy prompt không tự gửi nội dung đến AI.

`Import translations` mở màn hình review trước khi Apply:

- Tổng số matched, changed, unchanged, missing, extra và duplicate IDs.
- So sánh text trước/sau; cảnh báo timing bị thay đổi.
- Mặc định chỉ nhập translation, giữ timing/source/speaker/style.
- Match theo cue ID. Với SRT, đối chiếu timing và thứ tự; nếu mơ hồ phải cho người dùng review, không gán âm thầm.
- Lỗi cấu trúc chặn Apply; cảnh báo ngữ nghĩa cho phép tiếp tục có ghi nhận.
- Apply atomically một revision; không nhập một nửa rồi thất bại.
- Chỉ cue thay đổi nội dung TTS mới cần regenerate; các WAV còn lại vẫn được tham chiếu.

### 10.4 Voice và Resources đồng bộ

Voice panel có Output language, Engine, Voice, Voice type, Speed, Preview và `Manage voice engines`. Output language theo target language dự án; tool TTS độc lập có lựa chọn riêng.

Nhãn ví dụ: `Piper [VN/EN] · Fast · Ready`, `ZeroTTS [VN] · Natural · Not installed`, `Kokoro-82M [EN] · Natural · Not installed`. Đây là mẫu hiển thị; ngôn ngữ và trạng thái lấy từ capability thật, không suy ra từ tên model. Mã nội bộ dùng `vi`, `en`; UI dùng VN/EN theo yêu cầu.

KorvaTTS hoặc engine tương lai chỉ có Install khi có integration và nguồn cài xác thực hoạt động. Nếu chưa tích hợp, đưa vào nhóm `Coming soon`, không cho chọn như engine dùng được.

Chọn engine chưa cài vẫn có thể xem thông tin và cài; nút Generate giải thích yêu cầu. Chọn EN lọc giọng VN và ngược lại. Khi đổi ngôn ngữ làm giọng cũ không hợp lệ, yêu cầu chọn giọng tương thích; không tự đổi về Piper âm thầm.

### 10.5 Audio và timeline

Mỗi track có tên, mute, solo, volume, lock và menu. Volume số và slider cùng một giá trị. Solo chỉ là trạng thái nghe thử theo mặc định; export summary thể hiện rõ nếu người dùng muốn áp dụng solo vào output.

`Audio Mix` cung cấp preset và Custom. Thay slider chuyển Custom; không thay preset ngoài ý muốn khi click cue. Stem Music/Voice và Dub là những nguồn độc lập, không đồng nhất tên file.

Timeline hỗ trợ select, drag, trim, delete, reorder, zoom, snap, undo/redo. Khóa track chặn thao tác sửa tương ứng. Thao tác nguồn video thay đổi phải cập nhật duration, time mapping, preview và export revision cùng nhau.

### 10.6 Export

Dialog gồm Output file, Resolution, FPS, Aspect ratio/Fit-Fill, Preset, Video bitrate, Captions và Audio tracks.

- Preset: Fast / Balanced / Maximum quality.
- Bitrate: Auto hoặc Custom kbps; ví dụ `2000 kbps`. Không nhầm kbps với KB/s.
- Không cam kết 2000 kbps phù hợp mọi độ phân giải/nội dung; file size chỉ ước tính có nhãn.
- Nếu stream copy đủ điều kiện, hiển thị `Original video stream`; custom bitrate không áp dụng. Muốn ép bitrate thì chuyển encode.
- GPU hiển thị theo encoder đã kiểm tra chạy được, không chỉ vì FFmpeg liệt kê tên.
- Output summary: nguồn timeline revision, caption track, audio tracks/gain/mute, preset, bitrate và output path local.
- Trước khi chạy, kiểm tra audio outdated và missing media. Cho lựa chọn regenerate hoặc xuất cấu hình hiện có một cách rõ ràng.

Job export khóa một snapshot revision. Nếu sửa project trong lúc export, output vẫn gắn revision ban đầu và UI ghi `Project changed since this export started`. Hoàn tất chỉ sau verify và công bố file output hợp lệ; không báo thành công cho file partial.

## 11. Tasks và tiến độ thật

### 11.1 Danh sách và chi tiết

Mỗi hàng có loại tác vụ, tên dự án, thiết bị, stage, progress, thời gian chạy và action. Filter Active/Completed/Failed/Cancelled. Detail drawer hiển thị input summary, các stage, kết quả và thông tin lỗi.

Các trạng thái cần phân biệt: Queued, Waiting for device, Preparing, Running, Finalizing, Completed, Failed, Cancelling, Cancelled, Interrupted. Mất heartbeat là tình trạng kết nối `Connection lost`, chưa đủ để kết luận job thất bại.

Chỉ có Pause nếu engine hỗ trợ checkpoint/pause thật. Cancel chuyển Cancelling đến khi worker xác nhận. Retry tạo attempt mới và giữ lịch sử lỗi cũ. Bấm Run nhiều lần không được nhân đôi tác vụ do request gửi lại.

### 11.2 Quy tắc đo

| Tác vụ | Thông tin hiển thị |
| --- | --- |
| Download model | Bytes downloaded / total, %, tốc độ; chưa biết total thì không có % giả |
| Extract/install/verify | Stage riêng; không giữ chữ Downloading 100% xuyên suốt |
| Transcript | Audio time/chunks đã xử lý nếu engine cung cấp; nếu chưa có thì tên bước + elapsed |
| TTS | Số cue hoàn tất / tổng cue, % của stage TTS |
| Separation | Chunk/frame thật nếu có; nếu không thì indeterminate |
| FFmpeg export | `out_time` / duration của output pass, thời gian media, speed và ETA khi đủ dữ liệu |

Ví dụ `TTS · 389/954 · 40.8%`, cuối cùng `✓ TTS completed — 954/954`. Nếu 2 cue lỗi: `Finished with errors — 952/954`, không báo 954 thành công.

Không dùng phần trăm pipeline tổng làm phần trăm TTS. Pipeline nhiều pass hiển thị `Pass 1 of 2` và progress của pass; tổng phần trăm chỉ có khi trọng số có cơ sở và được gọi là estimate. Đang verify/mux có thể hiển thị Finalizing sau khi encoding 100%.

UI cập nhật một dòng trạng thái thay thế liên tục. Technical details mở theo nhu cầu; warning/error giữ lịch sử có nhóm trùng và count. Người dùng có `Copy error details` đã bỏ token, key và dữ liệu nhạy cảm.

### 11.3 Đóng tab, sleep và reconnect

Đóng tab không dừng tác vụ đã được Companion nhận và lưu. Thoát Companion, tắt máy hoặc sleep có thể làm job gián đoạn. UI mô tả đúng điều này trước khi người dùng thoát Companion có job đang chạy.

Mở web lại lấy snapshot job, sau đó nhận event có sequence mới. Không chuyển về 0% vì component mount lại. Chỉ cung cấp Resume khi job có checkpoint; trường hợp khác là Restart/Retry.

## 12. Devices

Card thiết bị có tên, hệ điều hành, Companion version, Ready/Busy/Offline, Last seen, CPU/GPU capability và số job active. Chỉ hiển thị RAM/disk nếu Companion cung cấp mới; số cũ có timestamp.

Actions: Connect new device, Rename, Set preferred device, View tasks, Disconnect. Thu hồi thiết bị chặn lệnh và phiên cloud mới; nếu thiết bị offline thì không hứa đã xóa file hoặc dừng process local. Hiện `Revocation pending on device` khi cần.

Mỗi job có processing device cố định. Chuyển bộ chọn thiết bị để xem tài nguyên không tự di chuyển job. Muốn chạy project trên máy khác phải resolve media trước.

## 13. Resources

Màn hình có bộ chọn thiết bị, công cụ/language filter và nhóm Speech recognition, TTS, Separation, Video utilities. Download size, installed size và disk remaining là số thật khi biết, không dùng con số ước đoán như dữ liệu đã đo.

Card tài nguyên có tên, language badges, tính năng, trạng thái runtime/model riêng và CTA phù hợp:

| Trạng thái | CTA |
| --- | --- |
| Not installed | Install |
| Runtime installed, model missing | Download model |
| Downloading | Cancel; progress thật |
| Installing / Verifying | Trạng thái bước đang làm |
| Ready | Preview / Manage |
| Failed | Retry / Details |
| Incompatible | Requirements |
| Not integrated | Coming soon, không giả nút cài |

Flow cài: chọn đúng engine/language/voice → xem kích thước và yêu cầu → download → verify → ready → cập nhật Voice panel ngay. Không mặc định tải tất cả VN/EN hoặc tất cả engine. Gỡ model đang được job sử dụng bị chặn có lý do.

## 14. Results và lịch sử output

Mỗi artifact có tên, loại, duration/size nếu có, device, created time, project revision và status Present/Missing/Outdated. `Open folder` chạy trên thiết bị chứa file, chỉ hiện khi thiết bị có thể thực hiện. `Save a copy` qua browser chỉ hoạt động khi luồng truyền media local được hỗ trợ.

Thiết bị khác/offline hiển thị `Available on My PC` thay cho nút Download vô tác dụng. Bản đầu không truyền file lớn qua cloud mặc định. Hỗ trợ xuất SRT từ nội dung đã sync; chuyển media giữa các máy là giai đoạn sau.

## 15. Settings, dữ liệu và quản trị

### 15.1 User settings

- Profile và session: tên, tài khoản, đăng xuất các phiên.
- Appearance: theme và density; UI English mặc định thống nhất.
- Defaults: source/target language, voice ưu tiên theo language, export preset/bitrate.
- Sync: metadata, tùy chọn sync subtitle text, trạng thái và lần thành công cuối.
- Local storage: thư mục dự án/output, quota cache, chỉ chỉnh khi thiết bị online.
- Providers: nhà cung cấp dịch, credential cấu hình trong Companion; web chỉ thấy configured/not configured.
- Notifications: completed, failed, device disconnected; browser notification opt-in.

### 15.2 Clear data và Delete

Tách rõ ba thao tác: `Clear temporary files`, `Remove generated outputs`, `Delete project`. Dialog liệt kê loại dữ liệu và phạm vi trên máy/cloud. Không gộp model vào clear project.

Clear derived data tăng revision/generation để kết quả từ job cũ không tái xuất hiện. Dừng hoặc bỏ áp dụng event/artifact thuộc generation cũ. Xóa cloud metadata khi thiết bị offline không được báo đã xóa file trên máy; hiển thị phần đang chờ.

Sau clear transcript/translation, preview không load lại ASS/SRT cache cũ. Chữ đã burn-in trong video nguồn vẫn tồn tại, có giải thích bằng một câu ngắn.

### 15.3 Admin tối thiểu

Khu vực chỉ dành cho administrator: số tài khoản, job metadata tổng hợp, lỗi theo loại, mức dùng API/storage, trạng thái phiên bản Companion và feature availability. Có phân trang và kiểm soát quyền ở backend.

Admin có thể giới hạn request, khóa tài khoản bị lạm dụng hoặc tắt tính năng chưa ổn định. Không mặc định truy cập media, transcript hoặc điều khiển file trên máy người dùng. Ghi audit cho thay đổi quản trị.

## 16. Hợp đồng đồng bộ bắt buộc

### 16.1 Nguồn dữ liệu chuẩn

- Cloud chuẩn cho tài khoản, device ownership và metadata quản lý.
- Companion chuẩn cho media, model, trạng thái xử lý thực tế và project revision đã áp dụng local.
- Web có draft edit; gửi mutation kèm base revision và mutation ID.
- Nếu bật đồng bộ subtitle, cloud giữ bản đã xác nhận theo revision; không ghi đè file local chỉ vì bản cloud có timestamp mới hơn.

Hiện riêng `Saved locally` và `Synced`. Nếu chưa kết nối máy, hiện `Draft saved in browser` thay vì Saved. Khi revision conflict, hiển thị compare và chọn giữ/áp dụng; không dùng last-write-wins cho toàn bộ timeline.

### 16.2 Phạm vi invalidation

| Thao tác | Tác động đúng |
| --- | --- |
| Select/right-click cue | Chỉ selection/menu |
| Sửa translation cue A | Audio A outdated, mix/export liên quan outdated |
| Sửa style | Render preview/export outdated; giữ WAV |
| Sửa timing | Kiểm tra alignment, dựng mix nếu cần; giữ audio tổng hợp có thể tái dùng |
| Đổi volume/mute | Mix/export outdated; không tổng hợp lại text |
| Đổi engine/voice | Chỉ cue trong phạm vi áp dụng outdated |
| Move/remove source video | Timeline time mapping và artifact phụ thuộc cần cập nhật |
| Clear generated data | Thu hồi artifact đúng phạm vi; loại event generation cũ |

Mọi mutation có undo khi khả thi. Undo khôi phục tham chiếu artifact còn hợp lệ, không phải mặc định tạo lại tất cả voice.

### 16.3 Schema tối thiểu đề xuất

| Entity | Trường thiết yếu |
| --- | --- |
| Project | id, owner_id, name, revision, generation, device_id, languages, updated_at |
| Asset | id, project_id, device_id, kind, fingerprint, duration, availability |
| Cue | id, project_id, start_ms, end_ms, original, translation, speaker_id, voice_config_hash |
| Job | id, owner_id, project_id, device_id, type, attempt, input_revision, state |
| Progress event | job_id, attempt, sequence, stage, current, total, unit, message, timestamp |
| Artifact | id, job_id, project_revision, kind, device_id, availability, size, duration |
| Device capability | device_id, protocol_version, engines, languages, voices, encoders, supported_actions |

Đường dẫn local được Companion map từ asset ID, không dùng request cloud như lệnh mở đường dẫn tùy ý. Cache audio có fingerprint của text, engine/model, voice và cấu hình ảnh hưởng âm thanh.

## 17. Kết nối kỹ thuật để giao diện hoạt động thật

Đề xuất TypeScript + React + Vite cho frontend, Tailwind cho token/component, Cloudflare Workers cho API nhẹ, D1 cho metadata và Python Companion cho xử lý. Đây là hướng kiến trúc, không phải danh sách dependency đã cài.

Có hai kênh cần thiết kế riêng:

1. Control/status: Companion chủ động kết nối ra cloud bằng phiên thiết bị đã xác thực. Bản đầu có thể dùng polling thích nghi, batch events và delta; không polling một giây liên tục cho mọi thiết bị. WebSocket là lựa chọn tối ưu tiếp theo khi đã đánh giá hạn mức và cơ chế điều phối.
2. Media local: phát video, waveform, picker/import và save output giữa browser cùng máy và Companion. Cần thử nghiệm HTTPS page ↔ loopback, quyền Local Network Access, CORS/Origin và seek/range của browser mục tiêu. Không mặc định mọi browser truy cập localhost được như nhau.

Companion chỉ nhận phiên local ngắn hạn gắn với origin được phép và asset đã được người dùng cấp quyền. Nếu môi trường chặn media local, hiển thị hướng dẫn cấp quyền hoặc `Open local workspace` do Companion phục vụ. Nếu fallback cần giao diện local riêng, giữ cùng frontend và thiết kế đăng nhập/pairing một lần; không đưa token cloud vào query string.

Máy khác/điện thoại có thể xem metadata/job qua cloud; không tự stream video từ PC qua Internet ở MVP. Mỗi job cần xác thực owner/device, idempotency, snapshot input, event sequence và journal local. Các phần này là yêu cầu bổ sung quanh workflow Python hiện có.

Không mở endpoint remote desktop đang dùng chung token cho nhiều tài khoản. Quyền truy cập, khóa project đang chạy và giới hạn đồng thời phải được kiểm tra ở backend/Companion, không chỉ disable nút web.

## 18. Nội dung lỗi và trạng thái rỗng

| Tình huống | Nội dung English đề xuất | Hành động |
| --- | --- | --- |
| Chưa kết nối | Connect your computer to process media. | Connect device |
| Máy offline | My PC is offline. Last seen 5 minutes ago. | Connection help |
| Thiếu model | This voice needs a model download. | Download model |
| Không rõ progress | Loading speech model… · 00:18 elapsed | Details |
| File mất | Source file could not be found on My PC. | Relink media |
| Job không được nhận | Waiting for your device to accept this task. | Cancel |
| Xung đột | This project changed on another session. | Review changes |
| Output cũ | This output was created from an earlier revision. | Export again |
| Không đủ ổ đĩa | Not enough free space for this task. | Manage storage |
| Lỗi tác vụ | Voice generation failed at cue 24. | Retry failed cues |
| Browser chặn local | Allow local connection to preview files on this computer. | Connection help |

Lỗi phải chỉ ra bước, ảnh hưởng và hành động tiếp theo. HTTP 500, stack trace, tên module hoặc FFmpeg stderr nằm trong Details. Không tự quy mọi lỗi Transcript cho TTS chỉ vì người dùng đang mở Voice panel.

## 19. Phím tắt và hành vi tương tác

Space: play/pause khi focus ngoài text input. Ctrl/Cmd+S: lưu draft và gửi sync nếu có. Ctrl/Cmd+Z: undo theo phạm vi editor. Delete: xóa đối tượng đang chọn khi ngoài input, không xóa file nguồn. Esc: đóng menu/dialog có thể đóng. Ctrl/Cmd+F: tìm trong bảng cue khi panel captions đang active.

Không override shortcut browser toàn cục nếu không cần. Right-click mở menu có thể dùng keyboard; double-click cue seek đến đầu cue. Khi có text đang sửa và selection thay đổi, lưu draft của text trước hoặc thông báo lỗi validation; không mất chữ.

## 20. Lộ trình triển khai và thứ tự màn hình

### Giai đoạn A — Nền móng và công cụ nhẹ

Thiết kế tokens/app shell, Sign in, Overview, Projects, SRT Editor trong browser. Làm spike kết nối Companion và media local trên Windows/Chrome/Edge. Chưa bật các nút media cho người dùng thật nếu pairing/file access chưa được kiểm chứng.

### Giai đoạn B — Companion và job thực tế

Devices, Resources, Tasks, Original Transcript, TTS và Separation. Bổ sung job protocol, cancellation, progress, results, reconnect và cài model theo capability. Hoàn tất một luồng input → xử lý → output thật cho từng tool.

### Giai đoạn C — Editor và export đồng bộ

Preview, captions, import translation, voice per cue, audio mix, timeline và export. Tích hợp revision/invalidation và kiểm tra file render so với lựa chọn người dùng.

### Giai đoạn D — Quản lý nâng cao

Admin, quản lý hạn mức, nhiều thiết bị, subtitle sync opt-in, template và chuyển dự án có relink. Chia sẻ file lớn hoặc live collaboration cần đặc tả riêng.

Mỗi giai đoạn chỉ công bố nút hoạt động end-to-end. Design prototype có thể thể hiện màn hình tương lai nhưng phải gắn nhãn rõ, không ghi Installed/Ready cho mock.

## 21. Tiêu chí nghiệm thu

| ID | Kịch bản | Kết quả bắt buộc |
| --- | --- | --- |
| WEB-01 | Hai tài khoản mở project/job ID của nhau | Backend từ chối, không lộ metadata |
| WEB-02 | Cài và pair lần đầu | Không cần nhập command/port/token |
| WEB-03 | Không có Companion | SRT Editor và quản lý vẫn dùng được; media CTA có giải thích |
| WEB-04 | Device offline trong khi chạy | Không bịa completion/failure; reconnect khôi phục trạng thái |
| WEB-05 | Đóng tab khi TTS đang chạy | Companion tiếp tục job đã nhận; mở lại có progress/result |
| WEB-06 | Máy sleep/restart | Interrupted rõ ràng, chỉ Resume khi có checkpoint |
| WEB-07 | Click/right-click cue | Không mất voice, đổi volume hoặc tự phát TTS |
| WEB-08 | Sửa một cue | Giữ audio cue khác, regenerate đúng phạm vi |
| WEB-09 | Import bản dịch reorder/thiếu/trùng cue | Review xác định lỗi, không ghép sai âm thầm |
| WEB-10 | Run to Original Transcript | Không tạo translation hoặc load translation cache cũ |
| WEB-11 | Cue ngắn, TTS dài | Phát hiện overflow, không âm thầm cắt nửa câu |
| WEB-12 | Đổi VN sang EN | Engine/voice/resources nhất quán, giữ lựa chọn hợp lệ |
| WEB-13 | Runtime đã cài nhưng thiếu weights | Hiện Download model, không Ready |
| WEB-14 | Separation hoàn thành | Hai stem đúng output, không giả bằng cùng audio nguồn |
| WEB-15 | Add stem và chỉnh volume/mute | Preview và export dùng đúng cấu hình snapshot |
| WEB-16 | Move/remove video | Preview/timeline/export cùng thứ tự, timing, duration |
| WEB-17 | Export | out_time thật, preset/bitrate đúng, file cuối phát được |
| WEB-18 | Export trong lúc sửa project | Output gắn revision đã chốt, không trộn revision |
| WEB-19 | Bấm Run hai lần/retry network | Một job logic, không tạo tác vụ trùng |
| WEB-20 | Clear data khi job cũ trả kết quả | Không hồi sinh artifact đã clear |
| WEB-21 | Dự án 1.000+ cues | Bảng/timeline chỉ render vùng cần; đo trên máy mục tiêu |
| WEB-22 | 1280×720, zoom 200%, mobile | Không mất CTA; có phương án panel/mobile rõ |
| WEB-23 | Browser không hỗ trợ codec/local access | Có fallback/hướng dẫn, không blank preview im lặng |
| WEB-24 | Media nằm trên máy khác | Không hiện Download/Play như thể file ở máy hiện tại |
| WEB-25 | Sync subtitle text tắt | Cloud không nhận transcript/translation payload |

Kiểm thử media dùng clip có lời nói và nhạc thật, có khoảng lặng, câu ngắn/dài và cue sát nhau. Kiểm tra bằng nghe và xem output, không chỉ unit test/ảnh UI. Ghi lại cấu hình, input fingerprint, output duration và case lỗi phát hiện; không tuyên bố “đúng toàn bộ” chỉ vì màn hình hiển thị thành công.

## 22. Bộ bàn giao khi triển khai giao diện

1. Component library: app shell, button, input, select, table, dialog, status badge, progress, device selector và empty/error states.
2. Màn hình đủ trạng thái loading/empty/ready/error/offline, không chỉ ảnh happy path.
3. Hợp đồng job/capability/revision và ví dụ payload đã thống nhất với Companion.
4. Luồng thật đã kiểm chứng: pair máy, chọn file, chạy một tool, reconnect, lưu output.
5. Báo cáo nghiệm thu theo WEB-01…WEB-25, ghi rõ case chưa hỗ trợ.
6. Hướng dẫn người dùng bằng English cho Download Companion, Connect, Install models, Run tools, Export và Clear data.

Tài liệu này là cơ sở để thiết kế và triển khai web. Các nút, route, schema và hành vi đề xuất cần được nối với backend/Companion và kiểm chứng trước khi coi là tính năng phát hành.
