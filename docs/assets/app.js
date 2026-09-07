// Tab metadata dictionary
const tourData = {
    workbench: {
        image: 'assets/screenshots/editor_with_subtitles.png',
        badge: 'Workspace Core',
        title: 'Studio Workbench & Multi-Track Editing',
        desc: 'Không gian làm việc hợp nhất giúp đồng bộ tức thì giữa trình phát video chất lượng cao, dòng thời gian đa track dạng sóng âm thanh và bảng thuộc tính chi tiết.',
        features: [
            { title: 'Multi-Track Timeline', icon: 'fas fa-layer-group', color: 'text-indigo-400', desc: 'Quản lý đồng thời video nguồn (V1), audio gốc (A1), phụ đề đã dịch (TS1), và các lớp hiệu ứng che mờ (Blur).' },
            { title: 'Subtitle Inspector', icon: 'fas fa-keyboard', color: 'text-emerald-400', desc: 'Chỉnh sửa trực tiếp câu dịch tiếng Việt, nghe thử câu thoại, và áp dụng nút bấm AI Rewrite viết lại văn phong kịch tính.' },
            { title: 'Realtime Player & Controls', icon: 'fas fa-play', color: 'text-cyan-400', desc: 'Nhúng trực tiếp libmpv hỗ trợ tua nhanh 2x, lùi tiến từng khung hình (frame-by-frame) và xem thử vùng che mờ.' },
            { title: 'Fast Preview (5s)', icon: 'fas fa-bolt', color: 'text-amber-400', desc: 'Kết xuất nhanh 5 giây video thành phẩm ngay lập tức để kiểm tra font chữ, vị trí phụ đề và độ khớp âm thanh trước khi xuất.' }
        ]
    },
    launcher: {
        image: 'assets/screenshots/launcher.png',
        badge: 'Project Hub',
        title: 'Project Launcher & Hardware Auto-Detection',
        desc: 'Màn hình khởi động thông minh tự động phát hiện phần cứng (CPU Mode hoặc NVIDIA GPU CUDA), quản lý lịch sử dự án và cung cấp công cụ cắt video nhanh.',
        features: [
            { title: 'Auto Hardware Detection', icon: 'fas fa-microchip', color: 'text-indigo-400', desc: 'Tự động kiểm tra driver NVIDIA và CUDA 12 để kích hoạt GPU mode, fallback an toàn về CPU mode trên máy phổ thông.' },
            { title: 'Recent Projects Cards', icon: 'fas fa-clock-rotate-left', color: 'text-emerald-400', desc: 'Hiển thị thẻ dự án kèm hình ảnh thu nhỏ, thời gian mở gần nhất và trạng thái công đoạn (TTS complete, Transcribed).' },
            { title: 'Split Video Pre-Processing', icon: 'fas fa-scissors', color: 'text-cyan-400', desc: 'Cắt nhỏ các file video dài thành nhiều phần ngắn để tối ưu hóa bộ nhớ và tăng tốc độ xử lý AI.' },
            { title: 'One-Click Project Ingestion', icon: 'fas fa-folder-plus', color: 'text-amber-400', desc: 'Khởi tạo dự án nhanh chóng chỉ bằng cách chọn file MP4/MKV hoặc kéo thả trực tiếp.' }
        ]
    },
    timeline: {
        image: 'assets/screenshots/timeline_detail.png',
        badge: 'Precision Editing',
        title: 'Timeline Đa Track Ảo Hóa Chuyên Sâu',
        desc: 'Được thiết kế chịu tải hàng chục ngàn câu phụ đề với công nghệ Viewport Virtualization, hiển thị dạng sóng âm thanh chuẩn PCM 16-bit và thước đo khung hình chính xác.',
        features: [
            { title: 'Audio Waveform Cache', icon: 'fas fa-water', color: 'text-indigo-400', desc: 'Dạng sóng âm thanh được trích xuất và lưu cache nhị phân, vẽ vector siêu nhanh mà không phải đọc lại file gốc.' },
            { title: 'Track Locking & Solo', icon: 'fas fa-lock', color: 'text-emerald-400', desc: 'Khóa từng track riêng biệt để tránh cắt nhầm clip khi đang biên tập phụ đề hoặc chỉnh sửa vùng mờ.' },
            { title: 'Cắt Clip Tức Thì (Hotkey S)', icon: 'fas fa-cut', color: 'text-cyan-400', desc: 'Cắt nhanh phụ đề hoặc video tại vị trí con trỏ playhead chỉ với một phím bấm duy nhất.' },
            { title: 'Selection Range Tool', icon: 'fas fa-arrows-left-right', color: 'text-amber-400', desc: 'Chọn một khoảng thời gian trên timeline để chạy nhận diện lại bằng mô hình khác hoặc render Fast Preview.' }
        ]
    },
    captions: {
        image: 'assets/screenshots/editor_captions_active.png',
        badge: 'AI Core Engine',
        title: 'Captions, Whisper ASR & Local LLaMA GGUF',
        desc: 'Trung tâm cấu hình nhận diện giọng nói và dịch thuật. Hỗ trợ mô hình LLaMA GGUF chạy trực tiếp trên máy không phụ thuộc internet và không tốn phí API.',
        features: [
            { title: 'Llama.cpp Local GGUF Engine', icon: 'fas fa-microchip', color: 'text-indigo-400', desc: 'Chạy trực tiếp các mô hình Qwen3-4B, Gemma ngay trên CPU/GPU của bạn với tốc độ cực nhanh.' },
            { title: 'Dual ASR: Whisper & SenseVoice', icon: 'fas fa-language', color: 'text-emerald-400', desc: 'Linh hoạt chuyển đổi giữa Faster-Whisper độ chính xác cao và SenseVoice siêu tốc độ cho phim Trung, Hàn, Nhật.' },
            { title: 'Scan Entire PC for Models', icon: 'fas fa-search', color: 'text-cyan-400', desc: 'Tự động quét ổ đĩa máy tính để tìm các file mô hình GGUF có sẵn và tích hợp ngay vào danh sách.' },
            { title: 'Cloud Translation Fallback', icon: 'fas fa-cloud', color: 'text-amber-400', desc: 'Hỗ trợ Google AI Studio (Gemini 2.5 Flash), OpenAI GPT-4o-mini, và fallback miễn phí Google Translate.' }
        ]
    },
    voice: {
        image: 'assets/screenshots/editor_voice_active.png',
        badge: 'Neural Audio',
        title: 'Voice & TTS Studio (Lồng Tiếng AI)',
        desc: 'Phòng thu lồng tiếng AI tự động hóa hoàn toàn. Tự động điều chỉnh tốc độ nói khớp với khung thời gian gốc và hỗ trợ gán giọng riêng cho từng diễn viên.',
        features: [
            { title: 'Piper Neural TTS (Offline)', icon: 'fas fa-volume-high', color: 'text-indigo-400', desc: 'Giọng đọc tiếng Việt truyền cảm (Ngọc Huyền, Tuấn Khang) chạy hoàn toàn trên máy tính không cần mạng.' },
            { title: 'Microsoft Edge TTS (Cloud)', icon: 'fas fa-cloud-arrow-up', color: 'text-emerald-400', desc: 'Giọng đọc trực tuyến chất lượng phòng thu với âm sắc tự nhiên như người thật (Hoài My, Nam Minh).' },
            { title: 'Per-Speaker Voice Assignment', icon: 'fas fa-users', color: 'text-cyan-400', desc: 'Gán từng giọng đọc nam/nữ riêng cho từng nhân vật sau khi chạy phân tách người nói (Speaker Diarization).' },
            { title: 'Voiceover Ducking', icon: 'fas fa-sliders', color: 'text-amber-400', desc: 'Tự động giảm âm lượng nhạc phim khi giọng thuyết minh vang lên để câu chuyện rõ ràng và cuốn hút.' }
        ]
    },
    style: {
        image: 'assets/screenshots/editor_style_active.png',
        badge: 'Visual Typography',
        title: 'Subtitle Style Presets & Tùy Biến Phụ Đề',
        desc: 'Thư viện mẫu kiểu chữ chuyên biệt cho video ngắn TikTok, YouTube Shorts và Facebook Reels với hiệu ứng đổ bóng, viền chữ dày và tô màu từ khóa.',
        features: [
            { title: 'TikTok & Shorts Presets', icon: 'fab fa-tiktok', color: 'text-indigo-400', desc: 'Mẫu chữ to, viền đen nổi bật, căn giữa màn hình dọc 9:16 giúp giữ chân người xem video ngắn.' },
            { title: 'YouTube Landscape Presets', icon: 'fab fa-youtube', color: 'text-emerald-400', desc: 'Mẫu chữ thanh thoát có nền mờ nhẹ tối ưu cho màn hình TV, máy tính và điện thoại xoay ngang.' },
            { title: 'Keyword Highlight', icon: 'fas fa-highlighter', color: 'text-cyan-400', desc: 'Tự động bôi màu nổi bật cho các từ khóa kịch tính trong câu tóm tắt phim để tăng tương tác.' },
            { title: 'Tùy biến Font & Vị trí', icon: 'fas fa-font', color: 'text-amber-400', desc: 'Chọn font Segoe UI, Inter, Montserrat, tùy chỉnh màu chữ RGB và kéo thả vị trí bất kỳ trên khung hình.' }
        ]
    },
    blur: {
        image: 'assets/screenshots/editor_blur_inspector.png',
        badge: 'Copyright Protection',
        title: 'Lớp Che Mờ Blur, Logo & Hiệu Ứng Mosaic',
        desc: 'Công cụ đắc lực chống quét bản quyền hình ảnh. Cho phép vẽ vùng che mờ logo kênh gốc, đài truyền hình hoặc phụ đề cũ với hiệu ứng ô vuông mosaic điện ảnh.',
        features: [
            { title: 'Interactive Bounding Box', icon: 'fas fa-vector-square', color: 'text-indigo-400', desc: 'Vẽ và thay đổi kích thước vùng che trực quan ngay trên màn hình xem trước video.' },
            { title: 'Blur Radius & Opacity', icon: 'fas fa-droplet', color: 'text-emerald-400', desc: 'Thanh trượt điều chỉnh độ mờ từ nhẹ đến đặc và độ trong suốt của lớp che.' },
            { title: 'Cinematic Mosaic Pixelate', icon: 'fas fa-border-all', color: 'text-cyan-400', desc: 'Bật chế độ ô vuông mosaic với thanh trượt tùy biến kích thước hạt từ 4px đến 48px.' },
            { title: 'Independent Timing & Split', icon: 'fas fa-clock', color: 'text-amber-400', desc: 'Quy định chính xác thời điểm xuất hiện và kết thúc của vùng mờ trên Timeline độc lập.' }
        ]
    },
    resource: {
        image: 'assets/screenshots/resource_manager.png',
        badge: 'Asset Pipeline',
        title: 'Trình Quản Lý Tài Nguyên AI (Resource Manager)',
        desc: 'Kiểm soát trạng thái toàn bộ mô hình AI và bộ thư viện phụ thuộc. Tự động kiểm tra tính hợp lệ và hỗ trợ tải về bằng một cú click chuột.',
        features: [
            { title: 'Trạng thái 3 Mức (Ready/Missing/Partial)', icon: 'fas fa-circle-check', color: 'text-indigo-400', desc: 'Nhìn thấy ngay mô hình nào đã sẵn sàng, mô hình nào cần tải thêm trước khi bắt đầu dự án.' },
            { title: 'One-Click Model Downloader', icon: 'fas fa-download', color: 'text-emerald-400', desc: 'Tải trực tiếp SenseVoice, Silero VAD, Whisper, Piper voices vào đúng thư mục dự án mà không cần giải nén thủ công.' },
            { title: 'Open Storage Folder', icon: 'fas fa-folder-open', color: 'text-cyan-400', desc: 'Nút bấm mở nhanh thư mục lưu trữ trên Windows Explorer để người dùng copy file mô hình offline.' },
            { title: 'CUDA 12 Runtime Verification', icon: 'fas fa-bolt', color: 'text-amber-400', desc: 'Tự động kiểm tra thư viện CUDA CTranslate2 để đảm bảo GPU NVIDIA hoạt động tối đa công suất.' }
        ]
    },
    autorecap: {
        image: 'assets/screenshots/auto_recap_dialog.png',
        badge: 'Automated Editing',
        title: 'Auto Edit Recap — Dựng Phim Bằng AI',
        desc: 'Hệ thống tự động hóa chuyển động camera giúp video recap đạt nhịp điệu lôi cuốn như kênh review phim triệu view mà không cần cắt ghép thủ công từng cảnh.',
        features: [
            { title: 'Smart Zoom & Motion Framing', icon: 'fas fa-magnifying-glass-plus', color: 'text-indigo-400', desc: 'Tự động zoom cận cảnh 105% - 115% vào các khoảnh khắc kịch tính hoặc câu thoại cao trào.' },
            { title: 'Pan Reframe Motion', icon: 'fas fa-arrows-up-down-left-right', color: 'text-emerald-400', desc: 'Tạo chuyển động lia máy tự nhiên theo phương ngang hoặc dọc giúp cảnh quay tĩnh trở nên sống động.' },
            { title: 'Horizontal Flip Tránh Bản Quyền', icon: 'fas fa-arrows-split-up-and-left', color: 'text-cyan-400', desc: 'Lật gương các cảnh quay lặp lại để tránh quét bản quyền, thông minh bỏ qua các cảnh có chữ.' },
            { title: 'Speed Adjustment Ramps', icon: 'fas fa-gauge-high', color: 'text-amber-400', desc: 'Tự động giảm tốc 0.9x ở cao trào và đẩy nhanh 1.15x ở đoạn chuyển cảnh để tạo nhịp điệu cuốn hút.' }
        ]
    },
    subtable: {
        image: 'assets/screenshots/subtitle_editor_dialog.png',
        badge: 'Batch Correction',
        title: 'Subtitle Table Editor — Bảng Biên Tập Phụ Đề Tập Trung',
        desc: 'Giao diện chỉnh sửa phụ đề dạng bảng phong cách Excel. Hỗ trợ tìm kiếm thay thế hàng loạt, viết lại bằng AI và xuất/nhập file Excel tiện lợi.',
        features: [
            { title: 'Find & Replace Toàn Diện', icon: 'fas fa-magnifying-glass', color: 'text-indigo-400', desc: 'Tìm kiếm và thay thế danh từ riêng, tên nhân vật, thuật ngữ phim trên toàn bộ hàng ngàn câu phụ đề.' },
            { title: 'Export & Import Excel (.xlsx)', icon: 'fas fa-file-excel', color: 'text-emerald-400', desc: 'Xuất bảng phụ đề ra file Excel để gửi dịch giả hoặc nạp lại bản dịch đã chỉnh sửa từ bên ngoài.' },
            { title: 'Batch AI Rewrite', icon: 'fas fa-wand-magic-sparkles', color: 'text-cyan-400', desc: 'Kêu gọi AI duyệt lại toàn bộ phụ đề để sửa lỗi ngữ pháp, rút gọn câu quá dài và đồng bộ văn phong.' },
            { title: 'Bảo Toàn Mốc Thời Gian (Timestamps)', icon: 'fas fa-shield', color: 'text-amber-400', desc: 'Chỉ thay đổi nội dung văn bản mà vẫn giữ nguyên tuyệt đối mốc thời gian Start/End và gán giọng của từng câu.' }
        ]
    }
};

function switchTourTab(tabKey) {
    const data = tourData[tabKey];
    if (!data) return;

    // Update tab button styles
    document.querySelectorAll('#tour-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.getElementById('tab-' + tabKey);
    if (activeBtn) activeBtn.classList.add('active');

    // Update Image
    const img = document.getElementById('tour-screenshot');
    if (img) {
        img.style.opacity = '0';
        setTimeout(() => {
            img.src = data.image;
            img.style.opacity = '1';
        }, 150);
    }

    // Update Info
    const badgeEl = document.getElementById('tour-badge');
    if (badgeEl) badgeEl.innerText = data.badge;
    const titleEl = document.getElementById('tour-title');
    if (titleEl) titleEl.innerText = data.title;
    const descEl = document.getElementById('tour-desc');
    if (descEl) descEl.innerText = data.desc;

    // Update features grid
    const container = document.getElementById('tour-features');
    if (container) {
        container.innerHTML = '';
        data.features.forEach(feat => {
            const card = document.createElement('div');
            card.className = 'p-3.5 rounded-xl bg-white/[0.03] border border-white/5';
            card.innerHTML = `
                <div class="text-xs font-semibold ${feat.color} flex items-center gap-2">
                    <i class="${feat.icon}"></i>
                    <span>${feat.title}</span>
                </div>
                <p class="text-[11px] text-slate-300 mt-1 leading-normal">${feat.desc}</p>
            `;
            container.appendChild(card);
        });
    }
}

// Markdown Reader Logic
const docsData = {
    'how-to-use': {
        file: 'docs/how-to-use.md',
        title: 'Hướng dẫn Sử dụng Chi tiết (User Guide)',
        content: `
            <h3>1. Khởi động & Chọn dự án (Launcher)</h3>
            <p>Khởi chạy ứng dụng qua <code>python ui/gui.py</code>. Chọn chế độ <strong>CPU Mode</strong> hoặc <strong>GPU Mode</strong>. Tạo dự án mới qua nút <strong>+ New Project</strong> hoặc chọn lại dự án trong danh sách <strong>Recent Projects</strong>.</p>
            
            <h3>2. Quy trình làm việc 5 bước (Prepare ➔ Transcript ➔ Translate ➔ Voice ➔ Export)</h3>
            <p>Cấu hình video nguồn tại tab <code>01 Source</code>, thiết lập ngôn ngữ và mô hình tại <code>03 Captions</code>, chọn giọng đọc tại <code>04 Voice</code> và bấm <strong>Generate</strong>.</p>
            
            <h3>3. Chỉnh sửa phụ đề trên Timeline</h3>
            <p>Chọn câu phụ đề trên track <strong>TS1</strong> để sửa câu dịch, chỉnh mốc thời gian, hoặc bấm <strong>AI Rewrite</strong> để viết lại kịch tính. Bấm nút <strong>Edit</strong> để mở bảng chỉnh sửa dạng bảng Excel.</p>
            
            <h3>4. Che mờ logo & chống bản quyền</h3>
            <p>Bấm nút <strong>Blur</strong> dưới màn hình video để tạo vùng che. Chỉnh độ mờ và kích thước hạt mosaic trên <strong>Blur Inspector</strong>.</p>
        `
    },
    'tech-stack': {
        file: 'docs/technical-stack.md',
        title: 'Kiến trúc Kỹ thuật & Công nghệ',
        content: `
            <h3>1. Nền tảng cốt lõi</h3>
            <p><strong>PySide6 (Qt 6.11)</strong> cung cấp giao diện desktop hiệu năng cao. Trình phát video <strong>libmpv</strong> cho phép tua và phát mượt mà không trễ.</p>
            
            <h3>2. Các bộ máy Trí tuệ Nhân tạo</h3>
            <ul>
                <li><strong>Faster-Whisper & SenseVoice:</strong> Nhận diện giọng nói với độ chính xác cao và mốc thời gian chi tiết.</li>
                <li><strong>RapidOCR PP-OCRv4:</strong> Quét phụ đề cứng trực tiếp từ khung hình video.</li>
                <li><strong>Llama.cpp & Google AI Studio:</strong> Bộ điều phối dịch thuật hỗ trợ cả offline mô hình GGUF và cloud API.</li>
                <li><strong>Piper & Edge TTS:</strong> Sinh âm thanh lồng tiếng tiếng Việt tự nhiên, truyền cảm.</li>
            </ul>
            
            <h3>3. Viewport Virtualization</h3>
            <p>Timeline chỉ tính toán và render các clip nằm trong khung nhìn hiển thị, đảm bảo không bao giờ giật lag ngay cả với hơn 10.000 câu thoại.</p>
        `
    },
    'project-structure': {
        file: 'docs/project-structure.md',
        title: 'Cấu trúc Thư mục & Mã nguồn',
        content: `
            <h3>Phân tầng Kiến trúc (Clean Architecture)</h3>
            <ul>
                <li><code>app/</code>: Tầng nghiệp vụ cốt lõi, bao gồm các workflows, dịch vụ (services), bộ máy AI (engines) và mô hình miền Timeline (layers).</li>
                <li><code>ui/</code>: Tầng giao diện người dùng PySide6, gồm cửa sổ chính, timeline ảo hóa, preview libmpv, thanh điều hướng và các Mixin tính năng.</li>
                <li><code>bin/</code>: Chứa các công cụ nhị phân thực thi đi kèm: FFmpeg, libmpv, CUDA 12 runtime pack.</li>
                <li><code>models/</code>: Thư mục lưu trữ các file trọng số AI tải về (Whisper, SenseVoice, Piper voices).</li>
                <li><code>docs/</code>: Cổng thông tin tài liệu tương tác và bộ ảnh chụp màn hình thực tế.</li>
            </ul>
        `
    },
    'requirements': {
        file: 'docs/requirements.md',
        title: 'Yêu cầu Hệ thống & Quản lý Tài nguyên',
        content: `
            <h3>1. Cấu hình máy tính khuyến nghị</h3>
            <p><strong>CPU Mode:</strong> Windows 10/11 64-bit, CPU 4 nhân (Intel i3/AMD Ryzen 3), 8 GB RAM, 10 GB ổ cứng trống.</p>
            <p><strong>GPU Mode (Khuyến nghị):</strong> NVIDIA RTX 2060 / 3060 trở lên (VRAM >= 6GB), 16 GB RAM. Tự động kích hoạt tăng tốc CUDA cho Whisper và OCR.</p>
            
            <h3>2. Tải tài nguyên tự động</h3>
            <p>Truy cập <strong>Manage Resources</strong> trong ứng dụng để tải SenseVoice (~237MB), Silero VAD (~2MB), Piper Voices (~60MB/giọng), và gói CUDA 12 (~450MB).</p>
        `
    },
    'shortcuts': {
        file: 'docs/keyboard-shortcuts.md',
        title: 'Bảng Tra cứu Phím tắt Nhanh',
        content: `
            <table class="w-full text-left text-xs border border-white/10 mt-2">
                <tr class="border-b border-white/10 bg-white/5 font-bold">
                    <th class="p-2 text-indigo-400">Phím tắt</th>
                    <th class="p-2">Thao tác</th>
                </tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">Space</td><td class="p-2">Bật / Tạm dừng phát video</td></tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">S</td><td class="p-2">Cắt (Split) clip hoặc phụ đề tại con trỏ</td></tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">Delete / Backspace</td><td class="p-2">Xóa clip đang chọn</td></tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">Ctrl + Z / Ctrl + Y</td><td class="p-2">Hoàn tác (Undo) / Làm lại (Redo)</td></tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">Ctrl + + / Ctrl + -</td><td class="p-2">Phóng to / Thu nhỏ Timeline</td></tr>
                <tr class="border-b border-white/5"><td class="p-2 font-mono text-emerald-400">F5</td><td class="p-2">Fast Preview 5 giây</td></tr>
                <tr><td class="p-2 font-mono text-emerald-400">Ctrl + E</td><td class="p-2">Mở bảng Xuất bản video (Export)</td></tr>
            </table>
        `
    },
    'troubleshooting': {
        file: 'docs/troubleshooting.md',
        title: 'Hướng dẫn Xử lý Sự cố Thường gặp',
        content: `
            <h3>1. Lỗi không nhận diện CUDA / GPU</h3>
            <p>Cập nhật NVIDIA Driver mới nhất từ trang chủ. Vào <strong>Manage Resources</strong>, tìm <strong>CUDA 12 Runtime Pack</strong> và bấm Download.</p>
            
            <h3>2. Tiếng thuyết minh bị lệch thời gian</h3>
            <p>Trong tab <code>04 Voice</code>, đặt <strong>Voice Timing Sync Mode</strong> thành <code>Smart</code>. Tăng nhẹ thanh <strong>Voice Speed</strong> lên 1.1x nếu câu thoại dài.</p>
            
            <h3>3. Phụ đề tiếng Việt bị vỡ chữ / lỗi font</h3>
            <p>Vào tab <code>05 Style</code> và chọn các font chuẩn Unicode: <strong>Segoe UI</strong>, <strong>Inter</strong>, <strong>Arial</strong> hoặc <strong>Montserrat</strong>.</p>
        `
    }
};

function loadDocContent(docKey) {
    const data = docsData[docKey];
    if (!data) return;

    document.querySelectorAll('.doc-btn').forEach(btn => {
        btn.classList.remove('active', 'border-indigo-500/50', 'bg-indigo-500/10', 'text-indigo-300');
        btn.classList.add('border-slate-700', 'bg-slate-900', 'text-slate-300');
    });
    const activeBtn = document.getElementById('doc-tab-' + docKey);
    if (activeBtn) {
        activeBtn.classList.remove('border-slate-700', 'bg-slate-900', 'text-slate-300');
        activeBtn.classList.add('active', 'border-indigo-500/50', 'bg-indigo-500/10', 'text-indigo-300');
    }

    const filenameEl = document.getElementById('doc-filename');
    if (filenameEl) filenameEl.innerText = data.file;
    const directLinkEl = document.getElementById('doc-direct-link');
    if (directLinkEl) directLinkEl.href = data.file.replace('docs/', '');
    const docBodyEl = document.getElementById('doc-body');
    if (docBodyEl) {
        docBodyEl.innerHTML = `
            <h2 class="text-xl font-bold text-white mb-4">${data.title}</h2>
            ${data.content}
        `;
    }
}

// Copy Install Commands Logic
function copyInstallCommands() {
    const commands = `git clone https://github.com/ViuGiaLai/VIUStudio.git
cd VIUStudio
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements-local.txt
python ui/gui.py`;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(commands).then(() => {
            const icon = document.getElementById('copy-icon');
            const text = document.getElementById('copy-text');
            if (icon) icon.className = 'fas fa-check text-emerald-400 text-[11px]';
            if (text) text.innerText = 'Đã sao chép!';
            setTimeout(() => {
                if (icon) icon.className = 'fas fa-copy text-[11px]';
                if (text) text.innerText = 'Sao chép lệnh';
            }, 2500);
        });
    }
}

// Ensure elements are hooked up on DOMContentLoaded if not already
document.addEventListener('DOMContentLoaded', () => {
    // If dynamic container not filled, initialize default doc
    const docBody = document.getElementById('doc-body');
    if (docBody && docBody.children.length === 0) {
        loadDocContent('how-to-use');
    }
    const tourContainer = document.getElementById('tour-features');
    if (tourContainer && tourContainer.children.length === 0) {
        switchTourTab('workbench');
    }
});
