# Kết quả BIRD Mini-Dev PostgreSQL

Model: `gpt-6-luna`; reasoning: low; mẫu: **120 câu đầu theo thứ tự dataset**, giữ cả câu sinh SQL lỗi.

Đây là đánh giá sơ bộ trên 3/11 database, không phải mẫu ngẫu nhiên đại diện toàn bộ 500 câu. Lượt sinh 500 câu vẫn chạy độc lập.

**VES đo khi lượt sinh 500 câu đang dùng chung PostgreSQL**, có thể bị ảnh hưởng bởi tải đồng thời; không dùng làm phép so hiệu năng cuối cùng.

Sinh SQL: 118 thành công, 2 trả SQL rỗng. EX: **42 đúng / 120**, 51 sai kết quả, 25 lỗi thực thi, 2 thiếu SQL.

CM/EM giữ alias và schema qualifier, vì vậy cách viết SQL khác có thể bị tính không khớp dù EX đúng; EM = 0 không có nghĩa là không câu nào chạy đúng.

CM/EM: PostgreSQL AST adaptation, không phải điểm Spider chính thức.

| Độ đo | Điểm (%) | Không chấm được |
|---|---:|---:|
| CM | 21.91 | 0 |
| EM | 0.00 | 0 |
| EX | 35.00 | 0 |
| VES | 35.28 | 0 |

## Theo db_id

| Nhóm | Số câu | CM | EM | EX | VES |
|---|---:|---:|---:|---:|---:|
| debit_card_specializing | 30 | 18.11 | 0.00 | 23.33 | 22.78 |
| student_club | 48 | 24.55 | 0.00 | 45.83 | 47.04 |
| thrombosis_prediction | 42 | 21.62 | 0.00 | 30.95 | 30.77 |

## Theo difficulty

| Nhóm | Số câu | CM | EM | EX | VES |
|---|---:|---:|---:|---:|---:|
| challenging | 22 | 16.52 | 0.00 | 18.18 | 18.18 |
| moderate | 56 | 19.95 | 0.00 | 33.93 | 33.96 |
| simple | 42 | 27.36 | 0.00 | 45.24 | 46.00 |
