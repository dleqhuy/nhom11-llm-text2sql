# mcp-text2sql

MCP server cho PostgreSQL, viết bằng Python + SQLAlchemy. Server cung cấp
hai tool `search_objects` và `execute_sql` qua Streamable HTTP tại
`http://127.0.0.1:7000/mcp`.

## Kiến trúc

MCP là adapter dữ liệu cho Codex, không phải API chat và không giữ trạng thái
thread. Codex là MCP client; backend cung cấp URL MCP khi khởi tạo Codex.

```text
Frontend ──> FastAPI ──> Codex MCP client
                           │ Streamable HTTP :7000/mcp
                           ▼
                      server.py (FastMCP tools)
                       ├─ search_objects.py ──> PostgreSQL catalogs
                       └─ execute_sql.py ──> sql_policy.py ──> SQLAlchemy Engine
                                                               └─ PostgreSQL
```

### Thành phần

- `server.py` nạp `.env`, tạo FastMCP Streamable HTTP server và SQLAlchemy engine,
  đăng ký tool, chuẩn hóa kết quả thành MCP text content JSON. Đây là entrypoint
  chạy bằng `uv run python server.py`.
- `mcp_text2sql/db.py` tạo engine/kết nối PostgreSQL dùng chung cho các tool.
- `mcp_text2sql/search_objects.py` truy vấn catalog PostgreSQL để khám phá schema,
  tables/views, columns, routines và indexes; có giới hạn kết quả và cấp độ chi tiết.
- `mcp_text2sql/execute_sql.py` chạy các statement và định dạng result set theo
  từng statement, cắt số dòng ở `MAX_ROWS`.
- `mcp_text2sql/sql_policy.py` kiểm tra chính sách SQL trước khi chạy. Khi
  `READONLY=true`, từ chối lệnh ghi và thực thi trong transaction chỉ đọc.
- `pyproject.toml` khai báo MCP SDK, SQLAlchemy, psycopg và sqlparse; `.env` cấu hình
  kết nối và giới hạn runtime, không commit credential.

Luồng truy vấn do Codex quyết định: thường gọi `search_objects` trước để tìm schema,
sau đó mới gọi `execute_sql`. Server MCP trả dữ liệu có cấu trúc và trạng thái lỗi;
Codex diễn giải kết quả thành câu trả lời cho người dùng. Nếu thay đổi tên tool hoặc
schema tham số, cần đồng bộ cấu hình `enabled_tools` ở backend và hướng dẫn tool cho Codex.

## Chạy

Cần Python 3.11 trở lên, `uv` và PostgreSQL có thể kết nối.
Từ thư mục gốc repo:

```bash
cd mcp-text2sql
cp .env.example .env
# Sửa DATABASE_URL trong .env.
uv sync
uv run python server.py
```

## Cấu hình

| Biến môi trường | Ý nghĩa                                   | Mặc định    |
| --------------- | ----------------------------------------- | ----------- |
| `DATABASE_URL`  | URL kết nối PostgreSQL của SQLAlchemy     | Bắt buộc    |
| `READONLY`      | Bật kiểm tra SQL và transaction chỉ đọc   | `true`      |
| `MAX_ROWS`      | Giới hạn số dòng trả về cho mỗi statement | `1000`      |
| `MCP_HOST`      | Địa chỉ server                            | `127.0.0.1` |
| `MCP_PORT`      | Port server                               | `7000`      |
| `SOURCE_ID`     | ID nguồn trong kết quả `execute_sql`      | `default`   |

Ví dụ URL: `postgresql+psycopg://postgres:postgres@localhost:5432/mydb`.
Giữ `READONLY=true` cho luồng hỏi đáp database chỉ đọc.

## Tools

- `search_objects(object_type, pattern="%", schema=None, table=None,
detail_level="names", limit=100)`: tìm schema, table, view, column,
  procedure, function và index; hỗ trợ chi tiết `names`, `summary`, `full`.
- `execute_sql(sql)`: chạy một hoặc nhiều SQL statements trong cùng
  transaction; trả kết quả theo từng statement với `sql`, `rows`, `count`
  và `truncated=true` khi vượt `MAX_ROWS`.

Tool trả JSON trong MCP text content. Lỗi có `success=false`, mã lỗi và
`isError=true`. Metadata discovery dùng các catalog riêng của PostgreSQL;
SQLAlchemy quản lý kết nối và thực thi.

## Kết nối ứng dụng

Chạy MCP trước backend. Backend cấu hình Codex kết nối qua
`MCP_URL=http://127.0.0.1:7000/mcp`; nếu đổi host hoặc port MCP, cập nhật
`MCP_URL` tương ứng. Backend không tự khởi động MCP.

Frontend hiển thị các lần gọi tool trong **Hoạt động database** của từng
lượt hỏi. Việc gắn tool với lượt hỏi dùng `turnId` từ SSE/lịch sử Codex ở FE;
MCP không quản lý hội thoại hoặc vị trí hiển thị.

Xem [backend README](../back-end/README.md) và
[frontend README](../front-end/README.md) để chạy toàn bộ ứng dụng.
