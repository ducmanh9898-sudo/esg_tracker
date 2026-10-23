# Hiển thị NeedsReview của BSR trong ESG Tracker

Chạy `python app.py`, mở `http://127.0.0.1:8050` và chọn **Đối chiếu BSR**. Mặc định bảng chọn **Phiên upload hiện tại**, nên sẽ trống trước khi upload. Chọn **Lượt BSR đã chạy trước** để xem một lần chạy được lưu trên chính máy này.

Với đúng sáu PDF BSR (ESG và BCTC hợp nhất cho từng năm 2023–2025), ứng dụng chạy Extract, tạo gói bàn giao và đối chiếu Graph. Trạng thái từng bước hiển thị tại mục upload; bảng Graph tự cập nhật. Nếu thiếu nguồn hoặc gói bàn giao không đạt kiểm tra cấu trúc, ứng dụng nêu lý do và không dùng kết quả cũ cho phiên hiện tại.

Mỗi dòng cho biết chỉ tiêu, hai báo cáo và trang PDF, chênh lệch, trạng thái `NeedsReview` (cần người duyệt). Chọn một dòng để xem câu nguồn, lý do và liên kết PDF. Chênh lệch chưa phải mâu thuẫn được xác nhận.

Graph nằm trong `knowledge_graph/` của repository này. Nếu muốn chạy Graph ở nơi khác, đặt `ESGTRACKER_GRAPH_REPO` thành đường dẫn gốc của Graph trước khi khởi động ứng dụng. Có thể đặt `ESGTRACKER_GRAPH_RUN_DIR` để chọn một lần chạy đã lưu trong thư mục Graph.

Phần giao diện hiện chỉ đọc kết quả; chưa lưu quyết định duyệt trở lại Graph.
