# Querydesk frontend

React + TypeScript + Vite, Tailwind CSS và shadcn/ui. Dependencies quản lý bằng Bun.

## Chạy frontend riêng

```bash
cd front-end
bun install --frozen-lockfile
bun run dev
```

Mở http://localhost:5173. Backend chạy ở port 8000; Vite proxy `/v1` và `/health`
tới backend. FastAPI chỉ phục vụ API, không phục vụ giao diện.

## Build và deploy riêng

```bash
bun run build
bun run preview
```

Build nằm trong `front-end/dist`; preview ở http://localhost:4173.
Nếu deploy khác domain, đặt URL backend trước khi build:

```bash
VITE_API_URL=https://api.example.com bun run build
```

Host nội dung `dist` bằng static hosting hoặc web server. Backend cần đặt
`BACKEND_CORS_ORIGINS=["https://app.example.com"]` để cho phép domain frontend.
`VITE_API_URL` áp dụng cho cả fetch API và EventSource SSE.

## Chức năng

- Tạo và tìm cuộc trò chuyện, tải thêm danh sách phân trang.
- Xóa hội thoại bằng nút thùng rác trong sidebar, có xác nhận xóa vĩnh viễn.
- Đọc lịch sử từ Codex, gửi turn mới vào cùng thread.
- SSE với `eventCursor`, hiển thị text và trạng thái MCP tools.
- Khối **Hoạt động database** nằm dưới các tin nhắn của từng lượt hỏi; số lần
  gọi, tham số, kết quả, lỗi và thời gian chạy được hiển thị riêng cho lượt đó.
- Tin nhắn và tool được gắn `turnId` ở cả stream và lịch sử; gửi câu hỏi mới
  hoặc tải lại chat không đẩy hoạt động của lượt cũ xuống cuối cuộc trò chuyện.
- Lượt không gọi tool không có khối hoạt động. Steer thuộc turn đang chạy.
- Bổ sung hướng dẫn (steer) và dừng phản hồi (interrupt).
- Hiển thị Markdown, bảng và SQL; sao chép câu trả lời.
- Menu responsive cho màn hình hẹp.

## Kiểm tra

```bash
bun run test
bun run lint
bun run build
```

Unit tests dùng API giả lập, bao gồm kiểm tra hoạt động database giữ đúng
lượt khi có câu hỏi mới và số lần gọi được tách riêng cho mỗi lượt.
Build kiểm tra TypeScript; lint dùng oxlint. Các kiểm tra này chưa xác nhận
chat với Codex/database thật.

Để kiểm tra thủ công, chạy MCP và backend rồi gửi hai câu hỏi liên tiếp có
truy vấn database. Mở khối hoạt động của từng lượt, kiểm tra số lần gọi và
kết quả; tải lại trang và chọn lại hội thoại để xác nhận vị trí vẫn đúng.
Thử thêm một lượt không gọi tool để kiểm tra không xuất hiện khối hoạt động
của lượt trước ở cuối chat.

## Format code

```bash
bun run format          # Format bằng Prettier
bun run format:check    # Kiểm tra format, không sửa file
```

Prettier format TypeScript, TSX, CSS, JSON và Markdown; oxlint kiểm tra lỗi code.
