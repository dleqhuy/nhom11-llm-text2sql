# Đánh giá BIRD Mini-Dev PostgreSQL

## Thí nghiệm này chạy gì?

- Model: **gpt-6-astra**, reasoning effort **low**, qua OpenAI Codex SDK.
- Đầu vào: `mini_dev_pg-00000-of-00001.json`, **500 câu / 11 database**.
- Prompt: question + evidence + db_id; không đưa SQL chuẩn vào prompt.
- Agent dùng MCP `search_objects`, `execute_sql` để tìm schema và thử SQL.
- Cài đặt hiện tại gộp các miền dữ liệu trong **BIRD.public**. Agent nhìn thấy
  toàn bộ schema này. Đây là điều kiện thí nghiệm riêng, không phải cách ly
  database như benchmark gốc. Không được so trực tiếp như một kết quả leaderboard.
- BIRD-Interact-ADK là benchmark tương tác khác, không phải tên dataset này.
- Mỗi câu có thread ephemeral riêng. Dataset và cấu hình được băm/ghi manifest;
  chạy lại `generate` cùng thư mục bỏ qua câu thành công, thử lại câu lỗi.
- SQL chuẩn chỉ được dùng trong preflight và chấm điểm; agent được hướng dẫn
  không đọc file đáp án. Đây là ràng buộc prompt, chưa phải cách ly filesystem.

## Các file mã nguồn

| File | Vai trò |
|---|---|
| `run.py` | CLI, checkpoint, điều phối sinh SQL và chấm |
| `metrics/components.py` | Parse PostgreSQL thành thành phần AST |
| `metrics/cm.py` | Precision/recall/F1 theo thành phần |
| `metrics/em.py` | Khớp toàn bộ thành phần |
| `metrics/ex.py` | Chạy SQL, lấy đầy đủ kết quả và so tập hàng |
| `metrics/ves.py` | Đo thời gian các câu trả lời đúng |
| `../scripts/generate_sql.py` | Sinh SQL bằng Codex + MCP |

## Chạy từ thư mục back-end

```bash
uv sync --group evaluation
# Khởi động MCP trước trong terminal khác: cd ../mcp-text2sql && uv run python server.py
uv run --group evaluation python -m evaluation.run preflight --output results/gpt-6-astra-mini-dev-pg
uv run --group evaluation python -m evaluation.run generate --output results/gpt-6-astra-mini-dev-pg --model gpt-6-astra
uv run --group evaluation python -m evaluation.run evaluate --output results/gpt-6-astra-mini-dev-pg
```

Có thể thay ba lệnh trên bằng một lệnh `python -m evaluation.run all --output results/gpt-6-astra-mini-dev-pg --model gpt-6-astra` trong môi trường đã cài dependency.

Kết nối chấm mặc định đọc `DATABASE_URL` từ `mcp-text2sql/.env`; có thể đặt
`EVALUATION_DATABASE_URL` để ghi đè. MCP phải trỏ cùng database. Không lưu mật
khẩu vào manifest. Tất cả truy vấn chấm dùng transaction chỉ đọc, timeout 30s.
`--concurrency 4` điều khiển sinh SQL; `--repetitions 5` điều khiển số vòng VES.

## Định nghĩa điểm — đọc trước khi sử dụng trong luận văn

**CM (postgres-ast-v1)**: SELECT, WHERE, GROUP BY, ORDER BY, keywords và structure
(FROM/JOIN/HAVING/LIMIT/DISTINCT cùng phần cấu trúc còn lại). Mỗi thành phần dùng
multiset, tính `P = match/pred`, `R = match/gold`, `F1 = 2*match/(pred+gold)`.
CM mỗi câu là trung bình F1 các thành phần có mặt ở ít nhất một phía; thành phần
rỗng cả hai phía không cộng điểm. Điểm tập dữ liệu là trung bình 500 câu × 100.

**EM (postgres-ast-v1)**: mọi multiset thành phần phải trùng nhau. Bỏ qua thứ tự
các phần tử trong thành phần và định dạng/ký tự hoa thường của identifier không
quote; giữ giá trị literal, DISTINCT, alias, hướng sắp xếp và cấu trúc truy vấn
con. Alias khác tên có thể bị tính sai. Không chuẩn hóa theo khóa ngoại/schema.
Cấu trúc truy vấn con hoặc UNION được so bảo thủ nên SQL tương đương có thể sai.

**CM/EM ở đây là bản thích nghi PostgreSQL, KHÔNG phải evaluator Spider chính
thức**. Spider có parser, chuẩn hóa giá trị, DISTINCT, khóa ngoại và cách tổng
hợp riêng. Khi báo cáo hãy ghi đúng tên giao thức `postgres-ast-v1`. Muốn điểm
Spider chính thức cần bộ schema/tables metadata và adapter tương thích được
kiểm chứng, không được đổi nhãn các điểm hiện tại.

**EX**: `100/N * sum(correct_i)`, so tập hàng của predicted SQL và gold SQL trên
cùng snapshot repeatable-read. Bỏ thứ tự hàng và số lần lặp hàng; giữ thứ tự cột
và giá trị. Không dùng kết quả MCP vì MCP giới hạn số hàng. Câu lỗi/thiếu SQL
nhận 0. Kết quả trùng trên database này chưa chứng minh tương đương mọi database.

**VES**: `100/N * sum(correct_i * sqrt(mean(t_gold/t_pred)))`. Chỉ đo câu EX đúng;
1 vòng warmup không tính điểm, 5 vòng đo mặc định, đảo thứ tự chạy giữa các vòng.
Mỗi vòng kiểm tra lại kết quả. Thời gian đo phía client gồm thực thi và lấy hàng,
qua mạng; không gồm thời gian sinh SQL. Không chạy song song khi đo VES. Điểm có
thể vượt 100 nếu SQL dự đoán nhanh hơn SQL chuẩn. Đây là thích nghi PostgreSQL;
khác môi trường, số vòng và chính sách lọc outlier của script BIRD gốc.

Lỗi SQL chuẩn/kết nối khiến EX/VES không thể chấm phải được xử lý trước khi kết
luận: không đổi chúng thành lỗi model hoặc âm thầm loại khỏi mẫu số. Summary
đặt điểm metric là `null` nếu có câu không chấm được. Luôn xem `statuses`.

## File kết quả

- `manifest.json`: model, reasoning, SHA256 dataset, số câu/database, giao thức.
- `preflight.json`: kiểm tra EXPLAIN SQL chuẩn; **không phải điểm model**.
- `predictions.csv`: bảng UTF-8 cho Excel, xuất sau khi chấm xong.
- `predictions.json`: câu hỏi, SQL chuẩn, `generated_sql`, trạng thái/lỗi sinh SQL.
- `cm.json`, `em.json`, `ex.json`, `ves.json`: điểm và lỗi từng câu riêng biệt.
- `summary.json`: tổng hợp toàn bộ, theo database và theo difficulty.
- `report.md`: bảng điểm dễ đọc; N/A nghĩa là chưa có điểm hợp lệ.

Chưa có `summary.json`/`report.md` thì chưa có kết quả chấm cuối cùng.

## Nguồn định nghĩa

- Dataset: https://huggingface.co/datasets/birdsql/bird_mini_dev
- Spider evaluator: https://github.com/taoyds/spider/blob/master/evaluation.py
- BIRD Mini-Dev VES: https://github.com/bird-bench/mini_dev/blob/main/evaluation/evaluation_ves.py
- Benchmark tương tác: https://github.com/bird-bench/BIRD-Interact/tree/main/BIRD-Interact-ADK
