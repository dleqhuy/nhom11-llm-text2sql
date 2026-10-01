# text2sql-codex

Ứng dụng hỏi đáp PostgreSQL bằng ngôn ngữ tự nhiên. Frontend Querydesk gửi câu hỏi
qua FastAPI tới Codex; Codex dùng MCP để tìm schema và chạy SQL.

## Thành phần

| Thư mục                                | Vai trò                                           | Địa chỉ local             |
| -------------------------------------- | ------------------------------------------------- | ------------------------- |
| [front-end](front-end/README.md)       | React + TypeScript, giao diện chat                | http://localhost:5173     |
| [back-end](back-end/README.md)         | FastAPI, quản lý thread/turn và SSE               | http://127.0.0.1:8000     |
| [mcp-text2sql](mcp-text2sql/README.md) | MCP PostgreSQL, `search_objects` và `execute_sql` | http://127.0.0.1:7000/mcp |

## Chạy local

Cần Python 3.12 trở lên, `uv`, Bun, PostgreSQL và thông tin đăng nhập Codex
hoặc `OPENAI_API_KEY`. Chạy ba thành phần trong ba terminal riêng.

### 1. MCP database

```bash
cd mcp-text2sql
cp .env.example .env
# Sửa DATABASE_URL trong .env để trỏ tới PostgreSQL của bạn.
uv sync
uv run python server.py
```

### 2. Backend

```bash
cd back-end
uv sync --locked
uv run uvicorn app.main:app --reload
```

Backend kết nối MCP qua `MCP_URL`, mặc định `http://127.0.0.1:7000/mcp`.
Chạy một worker vì runtime turn và bộ đệm SSE nằm trong bộ nhớ.
API: [Swagger](http://127.0.0.1:8000/docs).

### 3. Frontend

```bash
cd front-end
bun install --frozen-lockfile
bun run dev
```

Giao diện: [Querydesk](http://localhost:5173). Vite proxy API tới backend.
`bun run build` tạo `front-end/dist` để deploy riêng; xem hướng dẫn cấu hình
API URL và CORS trong [frontend README](front-end/README.md).

## Hoạt động database trong chat

Mỗi lượt hỏi có khối **Hoạt động database** dưới các tin nhắn của lượt đó.
Số lần gọi, trạng thái, tham số và kết quả tool được tính riêng theo `turnId`.
Khi gửi câu hỏi mới hoặc tải lại lịch sử, hoạt động cũ vẫn đi cùng lượt hỏi cũ.
Lượt không gọi tool không hiển thị khối này. Hướng dẫn bổ sung khi đang xử lý
(steer) vẫn thuộc cùng lượt hỏi.

## Kiểm tra

```bash
cd front-end
bun run test
bun run lint
bun run build
```

Kiểm tra backend từ thư mục `back-end` bằng `uv run pytest tests`.
Các test dùng SDK/API giả lập; để xác nhận tích hợp thực tế cần chạy cả ba
thành phần với Codex và PostgreSQL.

## Sinh SQL từ dataset JSON

Dùng script batch với thread riêng `ephemeral=True` cho mỗi câu hỏi. Xem
[hướng dẫn batch](back-end/README.md#sinh-sql-từ-file-json-batch) để cấu hình
MCP và xuất file kết quả.
