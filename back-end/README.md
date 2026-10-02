# FastAPI + AsyncCodex

Backend tối giản, dùng `uv` quản lý Python và dependencies.

## Cấu trúc

Tổ chức theo [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template/tree/master/backend),
với services cho Codex và SSE:

```text
back-end/
├── app/
│   ├── main.py              # Khởi tạo FastAPI và đăng ký routers
│   ├── models.py            # Pydantic request/response models
│   ├── crud.py              # Đọc/ghi registry thread JSON
│   ├── core/
│   │   ├── config.py        # Settings từ environment và .env
│   │   └── lifespan.py      # Vòng đời Codex client và runtime
│   ├── api/
│   │   ├── main.py          # Tổng hợp routers
│   │   ├── deps.py          # Dependencies Codex/runtime
│   │   └── routes/          # threads, turns, events, utils
│   └── services/            # Logic Codex, turn lifecycle, event buffer
├── tests/                   # API và lifecycle tests
├── scripts/test.sh          # Chạy pytest
├── data/threads.json        # Dữ liệu runtime, không đưa vào Git
├── .env.example
├── main.py                  # Entrypoint tương thích lệnh cũ
├── pyproject.toml
└── uv.lock
```

Thêm endpoint trong `app/api/routes/`, logic xử lý trong `app/services/`,
model trong `app/models.py`; đăng ký router tại `app/api/main.py`.
Đường dẫn registry vẫn là `back-end/data/threads.json`.
Copy `.env.example` thành `.env` nếu cần cấu hình; environment ưu tiên hơn `.env`.

## Chạy

```bash
cd back-end
uv sync --locked
# Nếu chưa đăng nhập Codex, đặt API key:
export OPENAI_API_KEY="your-api-key"
uv run uvicorn app.main:app --reload
```

Nếu đã đăng nhập Codex trên máy, có thể bỏ qua `OPENAI_API_KEY`.
SDK cài kèm Codex CLI. `POST /v1/threads` tạo thread mới với sandbox
chỉ đọc và chế độ `auto_review`. Các câu hỏi tiếp theo tạo turn trong cùng
thread qua `POST /v1/threads/{threadId}/turns`.
`AsyncCodex` được khởi tạo trong lifespan và dùng chung giữa các request;
client được đóng khi server dừng. Mỗi worker có một client riêng.
Thread được lưu bởi Codex (`ephemeral=False`). API lưu thêm ID, tên và thời gian
tạo (UTC) vào `data/threads.json`, ngay sau khi tạo thread, kể cả khi lượt
chat sau đó bị lỗi. File này được giữ qua các lần restart và không đưa vào Git.
Khóa file hỗ trợ nhiều worker trên macOS/Linux.

Swagger UI: <http://127.0.0.1:8000/docs>

## MCP PostgreSQL

Chạy MCP trong terminal riêng từ thư mục gốc repo:

```bash
cd mcp-text2sql
uv sync
# Cấu hình DATABASE_URL trong .env (xem .env.example).
uv run python server.py
```

Sau đó chạy backend. Lifespan truyền cấu hình `mcp_servers.text2sql`
cho Codex qua `CodexConfig.config_overrides`; URL mặc định là
`http://127.0.0.1:7000/mcp`. Có thể đổi URL bằng biến môi trường:

```bash
MCP_URL=http://127.0.0.1:7000/mcp uv run uvicorn app.main:app --reload
```

Codex dùng `search_objects` để tìm schema và `execute_sql` để chạy truy vấn.
MCP là bắt buộc (`required=true`), nên lỗi kết nối MCP sẽ khiến việc tạo
thread thất bại. Backend không tự khởi động MCP. Giữ `READONLY=true` tại MCP
để chỉ cho phép truy vấn đọc database.

## API v1: thread, turn và SSE độc lập

Chạy **một worker**. Runtime quản lý handles và events trong bộ nhớ;
khóa file JSON không chia sẻ runtime giữa các worker. Frontend sử dụng các endpoint `/v1` bên dưới.

| Endpoint                                               | Request / response                                                                                                                            |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /v1/threads`                                     | Body `{"prompt":"Câu hỏi ban đầu"}`; tùy chọn `name`. Trả 201 `{id,name,createdAt}`. Chỉ tạo thread và đặt tên, chưa chạy prompt.             |
| `POST /v1/threads/{threadId}/resume`                   | Không cần body. Trả `{threadId,status:"loaded"}`.                                                                                             |
| `GET /v1/threads?limit=20&cursor=...`                  | Trả `{data:[{id,name,createdAt}],nextCursor}`. Dùng `nextCursor` cho trang tiếp; null là hết. Liệt kê registry JSON của backend.              |
| `GET /v1/threads/{threadId}?includeTurns=true`         | Trả `{thread:...}` từ Codex; mặc định không tải turns.                                                                                        |
| `POST /v1/threads/{threadId}/turns`                    | Body `{"prompt":"Câu hỏi"}`. Tự resume; trả 202 `{threadId,turnId,status:"inProgress",eventCursor}` ngay sau khi bắt đầu.                     |
| `POST /v1/threads/{threadId}/turns/{turnId}/steer`     | Body `{"prompt":"Hướng dẫn bổ sung"}`. Chỉ nhận khi turn đang chạy.                                                                           |
| `POST /v1/threads/{threadId}/turns/{turnId}/interrupt` | Không cần body. Trả `interruptRequested` khi đã yêu cầu dừng; gọi lại không gửi lệnh dừng lần nữa. Chờ `turn/completed` để biết kết quả cuối. |
| `GET /v1/events?threadId=...&turnId=...&after=...`     | SSE, các bộ lọc tùy chọn. `turnId` cần `threadId`. Ngắt SSE không dừng turn.                                                                  |

Thread chưa đăng ký trong JSON / turn không tồn tại trả 404. Turn đang chạy
hoặc trạng thái không cho steer trả 409; body/cursor không hợp lệ trả 422.
Lỗi Codex trả 502, quá tải SDK trả 503. Sau restart, turn hoàn thành vẫn có
thể interrupt idempotently bằng lịch sử Codex, nhưng server không nhận quản lý
một turn đang chạy của client/server khác (409).

### Luồng frontend

Tạo thread, bắt đầu turn, rồi dùng `eventCursor` để đọc lại từ trước sự kiện
đầu tiên của turn. Không cần chờ SSE kết nối trước khi gửi prompt:

```javascript
const thread = await fetch("/v1/threads", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: "Liệt kê các bảng" }),
}).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
});
const turn = await fetch(`/v1/threads/${thread.id}/turns`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: "Liệt kê các bảng" }),
}).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
});
const query = new URLSearchParams({
  threadId: thread.id,
  turnId: turn.turnId,
  after: turn.eventCursor,
});
const stream = new EventSource(`/v1/events?${query}`);
stream.addEventListener("codex", (message) => {
  const event = JSON.parse(message.data);
  if (event.type === "item/agentMessage/delta") {
    console.log(event.data.delta);
  }
  if (event.type === "turn/completed" || event.type === "backend/error") {
    console.log(event.data);
    stream.close();
  }
});
stream.addEventListener("reset", () => {
  stream.close();
  // Tải GET /v1/threads/{id}?includeTurns=true rồi mở SSE mới.
});
```

SSE dùng event name `codex`; JSON có `{id,threadId,turnId,type,data}`.
`type` giữ tên sự kiện SDK, ví dụ `item/started`, `item/completed`,
`item/agentMessage/delta`, `turn/completed`; sự kiện backend gồm
`backend/turnStarted` và `backend/error`.
Frontend gắn tin nhắn và MCP tool calls với `turnId` của sự kiện; khi tải
lịch sử, lấy ID từ từng phần tử `thread.turns`. Nhờ đó, khối **Hoạt động database**
và số lần gọi nằm dưới đúng lượt hỏi, kể cả sau khi gửi câu hỏi mới hoặc
khôi phục lịch sử. Steer vẫn thuộc turn đang chạy.

Heartbeat mỗi 15 giây khi không có dữ liệu.
`turn/completed` có thể mang status `completed`, `failed` hoặc `interrupted`.

Buffer giữ tối đa 2.000 events toàn server. EventSource tự gửi `Last-Event-ID`
khi reconnect; header này được ưu tiên hơn query `after`. Cursor quá cũ hoặc
từ trước restart trả 409 khi kết nối; nếu client bị tụt lại khi đang stream,
server phát `reset` rồi đóng kết nối. Event buffer không tồn tại qua restart;
lịch sử thread vẫn được lưu bởi Codex. Server shutdown yêu cầu interrupt
các turn do `/v1` đang quản lý.

Chạy kiểm tra API với SDK giả lập:

```bash
uv run pytest tests
```

## Frontend độc lập

Frontend nằm ở `../front-end`, chạy riêng ở port 5173 và build vào `front-end/dist`.
FastAPI chỉ phục vụ API ở port 8000. Vite proxy `/v1` sang backend khi development.
Khi deploy khác domain, đặt `BACKEND_CORS_ORIGINS` bằng JSON array các origin
frontend được phép. Xem [frontend README](../front-end/README.md).

## Xóa cuộc trò chuyện

`DELETE /v1/threads/{threadId}` xóa vĩnh viễn trên Codex, rồi xóa ID trong registry
JSON và runtime. Thành công trả 204; thread đang chạy trả 409; ID không có trả 404.
SDK 0.159.3 chưa có hàm delete cấp cao, nên service dùng adapter RPC `thread/delete`.
Nếu runtime chưa hỗ trợ phương thức này, API trả 501 và giữ nguyên registry.
Frontend có nút thùng rác cạnh từng hội thoại và hộp xác nhận xóa.

## Format và lint

```bash
# Từ thư mục back-end
bash scripts/format.sh    # Sắp xếp imports và format bằng Ruff
bash scripts/lint.sh      # Kiểm tra lint và format, không sửa file
```

Ruff thuộc nhóm dependencies `dev`, được cài bằng `uv sync`.

## Sinh SQL từ file JSON (batch)

Script chạy độc lập với FastAPI; chỉ cần MCP đang chạy và Codex đã được xác thực.
Input là JSON array chứa `question_id`, `db_id`, `question`, tùy chọn `evidence`,
`SQL`, `difficulty`. Ví dụ chạy từ thư mục `back-end`:

```bash
uv run python scripts/generate_sql.py ../questions.json ../generated.json \
  --db-id debit_card_specializing --limit 2
```

Bỏ `--limit 2` để chạy toàn bộ câu hỏi của database đã chọn. Có thể đặt
`--mcp-url http://127.0.0.1:7000/mcp` và `--model` nếu cần; mặc định dùng
`MCP_URL` từ settings và model được Codex cấu hình.

- Mỗi câu hỏi tạo thread mới với `ephemeral=True`; script thu kết quả trực tiếp
  từ turn, không tải lịch sử và không ghi vào registry hội thoại của backend.
- Prompt chỉ chứa `db_id`, `question`, `evidence`. `SQL` tham chiếu không được
  gửi vào prompt; Codex được hướng dẫn không đọc dataset trên filesystem.
- Codex tìm schema qua MCP và trả SQL PostgreSQL theo JSON schema.
- Output giữ các trường input, thêm `generated_sql` và `generation_status`.
  Câu lỗi có `generated_sql=null`, `generation_error`; script tiếp tục câu sau.
- Lưu JSON sau mỗi câu bằng thay thế file tạm. Không ghi đè file output đã tồn tại
  và không cho dùng cùng đường dẫn input/output. Đây chưa phải cơ chế resume.
- Exit code là 1 nếu có câu sinh SQL thất bại; 0 nếu tất cả hoàn tất.

MCP hiện kết nối một PostgreSQL database. `--db-id` chỉ lọc dataset, không đổi
kết nối database. Bạn phải cấu hình `DATABASE_URL` của MCP đúng với `db_id`
đã chọn. Với dataset nhiều database, chạy riêng từng database và file output.
SQL sinh ra chưa được chấm độ chính xác so với SQL tham chiếu.

Kiểm tra script bằng SDK giả lập:

```bash
uv run pytest tests/test_generate_sql.py
```

## Chuẩn bị tập BIRD Mini-Dev 120 câu

Nguồn đã dùng: [BIRD Mini-Dev SQLite 500 câu](https://huggingface.co/datasets/birdsql/bird_mini_dev/tree/f65faf4ae3b638c1fa6df1d3370c8d92c8366301/data),
revision `f65faf4ae3b638c1fa6df1d3370c8d92c8366301`. Lưu file JSON vào
`data/bird_source/mini_dev_sqlite.json`, sau đó chạy từ thư mục `back-end`:

```powershell
uv run python -m scripts.prepare_bird --source data\bird_source\mini_dev_sqlite.json --output-dir data\bird_split --source-version f65faf4ae3b638c1fa6df1d3370c8d92c8366301 --seed 11
```

Chương trình kiểm tra `question_id`, `db_id`, `question`, `evidence`, `SQL`,
`difficulty`, đúng 500 câu và 11 database. Mỗi mức độ được lấy xoay vòng theo
database, với 36 `simple`, 60 `moderate`, 24 `challenging`. Cùng file nguồn và
seed sẽ tạo lại cùng danh sách ID, kể cả khi thứ tự các dòng nguồn thay đổi.

Kết quả trong `data/bird_split/` (thư mục `data/` không đưa lên Git):

- `test_en.json`: 120 câu kiểm tra, **không chứa SQL chuẩn**; dùng làm input sinh SQL.
- `gold_120.json`: SQL chuẩn của đúng 120 ID; chỉ bộ chấm điểm được đọc file này.
- `examples_380.json`: 380 câu còn lại kèm SQL, dành cho chiến lược few-shot.
- `manifest.json`: seed, phiên bản và SHA-256 nguồn, ID được chọn, phân bố độ khó
  và database để kiểm tra/tái lập việc lấy mẫu.

Chương trình không ghi đè bốn file đầu ra đã có. Bước này chưa dịch 120 câu sang
tiếng Việt, chưa xác minh SQL chuẩn bằng SQLite và chưa chạy mô hình/chấm EX.

## Kiểm tra SQL chuẩn trên BIRD SQLite

Đặt 11 file SQLite của cùng bản BIRD Mini-Dev vào
`data/bird_databases/<db_id>/<db_id>.sqlite` (hoặc
`data/bird_databases/<db_id>.sqlite`). Ví dụ:
`data/bird_databases/california_schools/california_schools.sqlite`.
Các file database chưa nằm trong repo. Sau khi có đủ 11 file, chạy từ `back-end`:

```powershell
uv run python -m scripts.check_bird_gold --db-root data\bird_databases
```

Lệnh chạy toàn bộ SQL trong `gold_120.json` chỉ để xác minh SQL thực thi được;
không dùng file gold làm prompt. Mỗi truy vấn mở SQLite chỉ đọc, giới hạn 5 giây
và 100.000 dòng; lệnh báo ID và lỗi của các câu không chạy được, trả exit code 1
khi còn lỗi. Đây chưa phải chấm EX giữa SQL sinh ra và SQL chuẩn. Để chạy test
độc lập với dữ liệu BIRD thật: `uv run pytest tests/test_bird_sqlite.py`.
