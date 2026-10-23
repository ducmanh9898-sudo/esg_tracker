# Giao diện Knowledge Graph cho người đọc không chuyên CNTT

## Người dùng và câu hỏi chính

Giao diện dành cho nhà đầu tư đang tham khảo thông tin BSR và chuyên gia phát triển bền vững đang tra cứu bằng chứng. Người đọc cần trả lời theo thứ tự: **điểm nào đáng chú ý → vì sao hệ thống nói vậy → số nào được đem so → tìm đoạn gốc ở đâu**. RDF, ID claim và guard code chỉ nằm trong phần truy vết mở rộng.

Trang local `output/bsr_demo/index.html` dùng dữ liệu pipeline BSR hiện hành. `graph_demo.html` là cùng một giao diện, mở được trực tiếp tại phần sơ đồ bằng chứng. Đây là bản đọc kết quả của demo BSR, không phải một đánh giá đầu tư hay kết luận tẩy xanh.

Mục **Đồ thị bằng chứng tương tác** trên trang chính cho phép chọn E/S/G hoặc liên kết ESG–BCTC. Mỗi lát cắt có các nút BSR, chỉ tiêu, phép kiểm tra, trạng thái và nguồn. Nét liền biểu thị đầu vào/đánh giá; nét đứt nối tới nguồn. Chọn nút bằng chuột hoặc Tab + Enter/Space để đọc giá trị, điều kiện và locator ở khung bên cạnh. Đồ thị này là phép chiếu các ca demo từ claim, evaluation và provenance của Graph v2; không hiển thị toàn bộ RDF ở một màn hình.

Mục **30 claim ESG** trình bày toàn bộ tập claim đã chọn trong demo, thay vì chỉ ba ca được chọn lên đồ thị. Mỗi dòng có năm báo cáo, năm đo nếu khác, chủ đề E/S/G, chỉ tiêu, giá trị, trạng thái phép kiểm tra, file/trang và truy vết ID/pointer. Bộ lọc theo năm, chủ đề và tìm kiếm hoạt động tại chỗ. Chỉ bảy claim 2025 có bằng chứng PDF chính thức đã đối chiếu giá trị/nhãn; các dòng khác ghi rõ locator từ Extract chưa được xác minh bằng PDF. “Chưa đánh giá bằng rule chính” không có nghĩa claim sai hoặc đúng.

Mục **Báo cáo tài chính** hiển thị một liên kết ứng viên giữa số lao động 1.594 trong báo cáo phát triển bền vững và 1.946 trong BCTC hợp nhất 2025. Thẻ nguồn ESG dùng trang 76 đã đối chiếu PDF; thẻ BCTC dùng tên file và trang 14 do JSON Extract khai báo. PDF BCTC không có trong workspace để đối chiếu độc lập. Graph giữ `comparable=false` vì ranh giới ESG, ngày chốt và định nghĩa lao động chưa được xác minh tương đồng. Chênh lệch 352 người chỉ là tín hiệu cần nghiên cứu tiếp.

## Quy tắc hiển thị

| Kết quả engine | Nhãn cho người đọc | Cách hiểu |
| --- | --- | --- |
| `Contradicted` | Có số liệu không khớp | Chỉ xuất hiện khi guard của phép kiểm tra đã đạt. Demo BSR 2025 hiện có **0** ca loại này. |
| `NeedsReview` | Cần kiểm tra thêm | Có số liệu liên quan nhưng thiếu context/nguồn để kết luận. |
| `Supported` | Phù hợp với phép kiểm tra | Chỉ xác nhận phép kiểm tra đang hiển thị, không nói doanh nghiệp bền vững hay tuân thủ mọi chuẩn. |
| `Skipped` | Chưa thể kiểm tra | Thiếu vai trò dữ liệu hoặc định nghĩa cần thiết; không tính là đạt. |

Mỗi thẻ chủ đề cho thấy chỉ tiêu, phép kiểm tra, trạng thái và lý do. Sơ đồ ngắn giữ các mối quan hệ có ích cho người đọc; danh sách nguyên văn nằm ngay bên dưới. Kết quả luôn có nhãn chữ, không dựa riêng vào màu. Người dùng có thể tìm theo chỉ tiêu, mục, trang hoặc tên tệp trong demo; tìm kiếm bỏ qua dấu tiếng Việt.

Nếu một ca khí thải thực sự đạt các guard và có kết quả `Contradicted`, sơ đồ sẽ đặt **Scope 1**, **Scope 2** và **tổng được công bố** cạnh phép tính; thẻ kết quả nêu hai vế, sai lệch và trạng thái bằng chữ. Mỗi số cần locator riêng tới báo cáo, trang, mục/bảng và nguyên văn. Đây là quy tắc hiển thị cho ca tương lai; ca E của BSR hiện vẫn `Skipped` vì chưa có tổng được định nghĩa rõ.

## Dẫn về báo cáo

Giao diện **không nhúng hoặc liên kết tới file PDF**. Thẻ nguồn chỉ ghi tên báo cáo, tên tệp được dùng trong demo, trang PDF vật lý, mục và bảng/đoạn, rồi hướng dẫn người đọc tự tìm bản báo cáo. Tên `BSR_2025_official.pdf` là tên tệp trong kho dữ liệu demo; tên để tìm báo cáo là *Báo cáo Phát triển Bền vững BSR 2025*. Trang 128–129 không được tráo với trang 65 của artifact Extract 68 trang.

Các trích đoạn 2025 hiển thị từ evidence node được đối chiếu với PDF chính thức và liên kết tới claim. Điều kiện chưa xác minh được nói rõ cạnh kết quả. Quan hệ giữa PDF chính thức 134 trang và binary PDF 68 trang do Extract khai báo chưa thể xác minh toàn bộ, vì binary 68 trang chưa có.

## Tình trạng BSR 2025 trong giao diện

- E: `Skipped`. Có Scope 1, Scope 2 và biến thể Scope 1; chưa có tổng được định nghĩa rõ là Scope 1 + Scope 2. Không hiển thị mâu thuẫn từ phép cộng tùy chọn.
- S: `NeedsReview`. Tổng 1.594 và nữ 214 cùng bảng, nhưng phương pháp đếm, kỳ và ranh giới tổ chức còn pending. Chênh lệch nam + nữ với tổng 27 người là issue riêng.
- G: `Supported` cho đúng câu “7 thành viên, trong đó 2 độc lập” ở trang 98. Không suy ngày snapshot chính xác, tính hợp pháp hoặc chất lượng quản trị.

Review nguồn của AI được giữ riêng với human adjudication. `technical_demo_pass=true` chỉ nói pipeline demo chạy và qua các check kỹ thuật; evidence acceptance của pilot vẫn pending.

## Mở rộng cho nhiều doanh nghiệp

Sơ đồ được dựng từ các claim và evaluation đã chọn theo config BSR, không thay ontology hoặc logic rule. Để mở rộng giao diện, cung cấp metadata hiển thị cho mỗi rule: câu hỏi tự nhiên, tên chỉ tiêu, nhãn trạng thái, rationale và locator đã được xác minh. Khi thiếu mục/bảng hoặc locator chưa đối chiếu PDF, hiển thị “chưa xác minh” thay vì tự đoán. Cần kiểm thử với người dùng thật trước khi coi đây là giao diện sản phẩm hoàn chỉnh.
