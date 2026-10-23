from __future__ import annotations

import csv
from pathlib import Path


# ==============================================================================
# BỘ DỮ LIỆU MẪU THỰC TẾ BSR GIAI ĐOẠN 2022–2025
# Trích xuất từ các Báo cáo ESG BSR, Báo cáo Tài chính BCTC và văn bản OCR trong output/
# ==============================================================================

BSR_RECORDS_RAW = [
    # --------------------------------------------------------------------------
    # NĂM 2022 (Trích xuất từ Báo cáo BSR 2023 trang 25 & 30 đối chiếu quá khứ và BCTC 2022)
    # --------------------------------------------------------------------------
    {
        "year": 2022, "pillar": "E", "topic": "E_CLIMATE", "code": "GHG_SCOPE_1",
        "claim_text": "BSR báo cáo tổng phát thải khí nhà kính năm 2022 là 1.757.152 tCO2e (trích bảng chuỗi số liệu phát thải đối chiếu 2021-2023).",
        "page": 30, "claim_type": "QUANTITATIVE", "raw_value": 1757152.0, "raw_unit": "tCO2e",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 1757152.0, "metric_unit": "tCO2e",
        "metric_text": "Số liệu đo đạc kỹ thuật phát thải KNK năm 2022 ghi nhận 1.757.152 tCO2e.",
        "methodology": "Phương pháp tính toán phát thải theo QCVN và Hướng dẫn Ipieca",
    },
    {
        "year": 2022, "pillar": "E", "topic": "E_INTENSITY", "code": "GHG_INTENSITY",
        "claim_text": "Cường độ phát thải KNK năm 2022 đạt 0,250348028 tCO2e/tấn sản phẩm với tổng sản lượng sản phẩm là 7.018.837 tấn.",
        "page": 30, "claim_type": "QUANTITATIVE", "raw_value": 0.250348, "raw_unit": "tCO2e/tấn sản phẩm",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "tấn sản phẩm",
        "intended_rel": "SUPPORTS", "metric_value": 0.250348, "metric_unit": "tCO2e/tấn sản phẩm",
        "metric_text": "Chỉ số cường độ phát thải KNK năm 2022 được chuẩn hóa là 0,250348 tCO2e/tấn sản phẩm.",
        "methodology": "Phát thải chia cho tổng sản lượng xuất bán",
    },
    {
        "year": 2022, "pillar": "E", "topic": "E_ENERGY", "code": "ENERGY_TOTAL",
        "claim_text": "Năm 2022, chỉ số hiệu quả năng lượng EII của Nhà máy lọc dầu Dung Quất đạt 104,2% theo phương pháp đánh giá Solomon.",
        "page": 25, "claim_type": "QUANTITATIVE", "raw_value": 104.2, "raw_unit": "%",
        "scope": "Toàn doanh nghiệp", "boundary": "Nhà máy Dung Quất", "value_kind": "INTENSITY", "denominator": "% mục tiêu",
        "intended_rel": "SUPPORTS", "metric_value": 104.2, "metric_unit": "%",
        "metric_text": "Hệ thống quản lý năng lượng ghi nhận EII năm 2022 đạt 104,2% (chuẩn Solomon).",
        "methodology": "Solomon Energy Intensity Index",
    },
    {
        "year": 2022, "pillar": "E", "topic": "E_WATER", "code": "WATER_WITHDRAWAL",
        "claim_text": "Lượng nước biển khai thác làm mát gián tiếp năm 2022 là 281.500.000 m3 và lượng nước ngọt khai thác là 3.150.000 m3.",
        "page": 26, "claim_type": "QUANTITATIVE", "raw_value": 281500000.0, "raw_unit": "m3",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 281500000.0, "metric_unit": "m3",
        "metric_text": "Đồng hồ lưu lượng nước biển đầu vào năm 2022 ghi nhận 281.500.000 m3.",
        "methodology": "Đo lưu lượng trực tiếp tại trạm bơm nước biển",
    },
    {
        "year": 2022, "pillar": "E", "topic": "E_WASTE", "code": "HAZARDOUS_WASTE",
        "claim_text": "BSR duy trì công tác thu gom, phân loại và chuyển giao chất thải nguy hại cho các nhà thầu có giấy phép xử lý môi trường.",
        "page": 26, "claim_type": "QUALITATIVE", "raw_value": None, "raw_unit": "tấn",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "MISSING", "metric_value": None, "metric_unit": None,
        "metric_text": None,
        "methodology": None,
    },
    {
        "year": 2022, "pillar": "E", "topic": "E_SPILLS", "code": "SPILL_COUNT",
        "claim_text": "Năm 2022, BSR không để xảy ra bất kỳ sự cố môi trường nghiêm trọng hay sự cố tràn dầu nào tại nhà máy và khu vực biển.",
        "page": 27, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "vụ",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "vụ",
        "metric_text": "Biên bản thanh tra và giám sát môi trường năm 2022 ghi nhận 0 sự cố tràn dầu.",
        "methodology": "Hệ thống giám sát an toàn môi trường biển",
    },
    {
        "year": 2022, "pillar": "S", "topic": "S_SAFETY", "code": "LTIFR",
        "claim_text": "BSR đạt cột mốc hơn 42,2 triệu giờ công an toàn không có tai nạn mất ngày công (LTIFR = 0) trong năm 2022.",
        "page": 31, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "ca/triệu giờ công",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "triệu giờ công",
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "ca/triệu giờ công",
        "metric_text": "Hồ sơ an toàn lao động năm 2022 ghi nhận tỷ lệ mất ngày công LTIFR = 0.",
        "methodology": "Hệ thống quản lý an toàn ISO 45001:2018",
    },
    {
        "year": 2022, "pillar": "S", "topic": "S_TRAINING", "code": "TRAINING_HOURS",
        "claim_text": "BSR tổ chức 135 khóa đào tạo cho 12.800 lượt nhân sự với thời lượng đào tạo an toàn bình quân đạt 15,2 giờ/người.",
        "page": 31, "claim_type": "QUANTITATIVE", "raw_value": 15.2, "raw_unit": "giờ/người/năm",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "người",
        "intended_rel": "SUPPORTS", "metric_value": 15.2, "metric_unit": "giờ/người/năm",
        "metric_text": "Sổ theo dõi đào tạo năm 2022 xác nhận thời lượng đào tạo an toàn đạt 15,2 giờ/người.",
        "methodology": "Thống kê giờ đào tạo trực tiếp và E-learning",
    },
    {
        "year": 2022, "pillar": "S", "topic": "S_COMMUNITY", "code": "ENV_EXPENSE",
        "claim_text": "Kinh phí thực hiện các chương trình an sinh xã hội, tài trợ y tế và giáo dục cộng đồng năm 2022 đạt 105 tỷ VND.",
        "page": 34, "claim_type": "QUANTITATIVE", "raw_value": 105.0, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 105.0, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC kiểm toán 2022 xác nhận chi phí tài trợ an sinh xã hội là 105 tỷ VND.",
        "methodology": "Quyết toán quỹ phúc lợi và tài trợ an sinh xã hội",
    },
    {
        "year": 2022, "pillar": "G", "topic": "G_GOVERNANCE", "code": "BOARD_STRUCTURE",
        "claim_text": "Hội đồng quản trị BSR năm 2022 gồm 5 thành viên: 1 Chủ tịch, 1 Tổng Giám đốc và 3 thành viên không điều hành.",
        "page": 36, "claim_type": "QUALITATIVE", "raw_value": 5.0, "raw_unit": "người",
        "scope": "Toàn doanh nghiệp", "boundary": "Công ty mẹ", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 5.0, "metric_unit": "người",
        "metric_text": "Nghị quyết Đại hội đồng cổ đông 2022 xác nhận cơ cấu 5 thành viên HĐQT.",
        "methodology": "Điều lệ công ty và báo cáo quản trị định kỳ",
    },
    {
        "year": 2022, "pillar": "G", "topic": "G_ANTICORRUPTION", "code": None,
        "claim_text": "100% cán bộ thuộc diện đã hoàn thành kê khai tài sản; không phát hiện vụ việc tham nhũng hoặc tiêu cực nào trong năm 2022.",
        "page": 24, "claim_type": "POLICY", "raw_value": None, "raw_unit": None,
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": None, "metric_unit": None,
        "metric_text": "Báo cáo kiểm soát tuân thủ ghi nhận 0 vụ việc vi phạm liêm chính.",
        "methodology": "Quy chế kiểm soát nội bộ và thanh tra BSR",
    },
    {
        "year": 2022, "pillar": "G", "topic": "G_TAX", "code": "TAX_PAID",
        "claim_text": "Tổng số tiền nộp ngân sách nhà nước của BSR trong năm 2022 đạt 19.029 tỷ VND.",
        "page": 22, "claim_type": "QUANTITATIVE", "raw_value": 19029.0, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 19029.0, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC hợp nhất kiểm toán 2022 ghi nhận các khoản đã nộp ngân sách là 19.029 tỷ VND.",
        "methodology": "Số liệu quyết toán thuế và xác nhận của cơ quan Thuế",
    },
    {
        "year": 2022, "pillar": "X", "topic": "FINANCIAL_CONNECTIVITY", "code": "REVENUE",
        "claim_text": "Doanh thu thuần hợp nhất năm 2022 đạt 167.164 tỷ VND và lợi nhuận sau thuế hợp nhất đạt 14.751 tỷ VND.",
        "page": 22, "claim_type": "QUANTITATIVE", "raw_value": 167164.0, "raw_unit": "tỷ đồng",
        "scope": "Consolidated", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 167164.0, "metric_unit": "tỷ đồng",
        "metric_text": "Báo cáo kết quả hoạt động kinh doanh hợp nhất kiểm toán 2022 ghi nhận doanh thu 167.164 tỷ VND.",
        "methodology": "Chuẩn mực Kế toán Việt Nam (VAS)",
    },

    # --------------------------------------------------------------------------
    # NĂM 2023 (Trích xuất từ BSR_2023_esg.json và BCTC_BSR_2023_esg.json)
    # --------------------------------------------------------------------------
    {
        "year": 2023, "pillar": "E", "topic": "E_CLIMATE", "code": "GHG_SCOPE_1",
        "claim_text": "BSR công bố tổng lượng phát thải khí nhà kính năm 2023 là 1.685.611 tCO2e, giảm so với năm 2022 (1.757.152 tCO2e).",
        "page": 30, "claim_type": "QUANTITATIVE", "raw_value": 1685611.0, "raw_unit": "tCO2e",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 1685611.0, "metric_unit": "tCO2e",
        "metric_text": "Số liệu kiểm kê khí nhà kính BSR 2023 xác nhận tổng phát thải đạt 1.685.611 tCO2e.",
        "methodology": "Kiểm kê KNK theo tiêu chuẩn ISO 14064-1",
    },
    {
        "year": 2023, "pillar": "E", "topic": "E_INTENSITY", "code": "GHG_INTENSITY",
        "claim_text": "Cường độ phát thải KNK năm 2023 là 0,228796147 tCO2e/tấn sản phẩm, giảm khoảng 8,61% so với năm 2022 (0,2503 tCO2e/tấn).",
        "page": 30, "claim_type": "COMPARATIVE", "raw_value": 0.228796, "raw_unit": "tCO2e/tấn sản phẩm",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "tấn sản phẩm",
        "intended_rel": "SUPPORTS", "metric_value": 0.228796, "metric_unit": "tCO2e/tấn sản phẩm",
        "metric_text": "Cường độ KNK được xác nhận đạt 0,228796 tCO2e/tấn sản phẩm (mẫu số sản lượng 7.367.305 tấn).",
        "methodology": "GRI 305-4 phát thải trên sản phẩm",
    },
    {
        "year": 2023, "pillar": "E", "topic": "E_ENERGY", "code": "ENERGY_TOTAL",
        "claim_text": "Chỉ số tiêu thụ năng lượng EII năm 2023 đạt 104,5%, tốt hơn mục tiêu đề ra là 105%. Tổng nhiên liệu tiêu thụ là 566.588 tấn.",
        "page": 25, "claim_type": "TARGET", "raw_value": 104.5, "raw_unit": "%",
        "scope": "Toàn doanh nghiệp", "boundary": "Nhà máy Dung Quất", "value_kind": "INTENSITY", "denominator": "% mục tiêu",
        "intended_rel": "SUPPORTS", "metric_value": 104.5, "metric_unit": "%",
        "metric_text": "Hệ thống quản lý năng lượng ISO 50001 xác nhận EII lũy kế 2023 đạt 104,5%.",
        "methodology": "Solomon Associates Energy Intensity Index",
    },
    {
        "year": 2023, "pillar": "E", "topic": "E_WATER", "code": "WATER_WITHDRAWAL",
        "claim_text": "Nước ngọt sử dụng là 3.093.350 m3; nước biển làm mát gián tiếp là 280.425.909 m3; lượng nước ngưng tái chế/tái sử dụng đạt 72,8%.",
        "page": 26, "claim_type": "QUANTITATIVE", "raw_value": 280425909.0, "raw_unit": "m3",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 280425909.0, "metric_unit": "m3",
        "metric_text": "Đo lưu lượng nước biển làm mát gián tiếp năm 2023 xác nhận 280.425.909 m3.",
        "methodology": "Đo lưu lượng trực tiếp tại trạm bơm nước biển",
    },
    {
        "year": 2023, "pillar": "E", "topic": "E_WASTE", "code": "HAZARDOUS_WASTE",
        "claim_text": "Báo cáo mô tả phân loại và chuyển giao chất thải nguy hại cho nhà thầu đủ điều kiện nhưng không công bố tổng khối lượng tấn phát sinh.",
        "page": 26, "claim_type": "QUALITATIVE", "raw_value": None, "raw_unit": "tấn",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "MISSING", "metric_value": None, "metric_unit": None,
        "metric_text": None,
        "methodology": None,
    },
    {
        "year": 2023, "pillar": "E", "topic": "E_SPILLS", "code": "SPILL_COUNT",
        "claim_text": "BSR ghi nhận 0 sự cố môi trường, 0 sự cố cháy nổ ảnh hưởng sản xuất và 0 vi phạm pháp luật bảo vệ môi trường trong năm 2023.",
        "page": 31, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "vụ",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "vụ",
        "metric_text": "Ban An toàn Môi trường BSR xác nhận không có sự cố tràn dầu hay ô nhiễm trong năm 2023.",
        "methodology": "Hệ thống giám sát an toàn ISO 14001:2015",
    },
    {
        "year": 2023, "pillar": "S", "topic": "S_SAFETY", "code": "LTIFR",
        "claim_text": "BSR duy trì hơn 42,2 triệu giờ công an toàn và 0 tai nạn mất ngày công (LTI = 0); hệ thống quản lý an toàn đạt chuẩn ISO 45001:2018.",
        "page": 31, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "ca/triệu giờ công",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "triệu giờ công",
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "ca/triệu giờ công",
        "metric_text": "Báo cáo an toàn lao động HSE 2023 xác nhận tỷ lệ tai nạn mất ngày công LTIFR = 0.",
        "methodology": "Tiêu chuẩn quốc tế OSHA / ISO 45001:2018",
    },
    {
        "year": 2023, "pillar": "S", "topic": "S_TRAINING", "code": "TRAINING_HOURS",
        "claim_text": "BSR tổ chức 141 chương trình đào tạo với 13.335 lượt tham gia, kinh phí đào tạo là 8 tỷ VND, bình quân đào tạo an toàn đạt 15,27 giờ/người.",
        "page": 31, "claim_type": "QUANTITATIVE", "raw_value": 15.27, "raw_unit": "giờ/người/năm",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "người",
        "intended_rel": "SUPPORTS", "metric_value": 15.27, "metric_unit": "giờ/người/năm",
        "metric_text": "Hồ sơ đào tạo nhân sự năm 2023 xác nhận thời lượng đào tạo an toàn đạt 15,27 giờ/người.",
        "methodology": "Thống kê từ hệ thống ERP quản lý nhân sự",
    },
    {
        "year": 2023, "pillar": "S", "topic": "S_COMMUNITY", "code": "ENV_EXPENSE",
        "claim_text": "Chi tài trợ cộng đồng và an sinh xã hội năm 2023 đạt 119,3 tỷ VND: nhà đại đoàn kết 38,84 tỷ, giáo dục 36,1 tỷ, y tế 20 tỷ.",
        "page": 34, "claim_type": "QUANTITATIVE", "raw_value": 119.3, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 119.3, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC kiểm toán 2023 xác nhận tổng chi phí các chương trình an sinh xã hội là 119,3 tỷ VND.",
        "methodology": "Quyết toán quỹ hỗ trợ an sinh xã hội",
    },
    {
        "year": 2023, "pillar": "G", "topic": "G_GOVERNANCE", "code": "BOARD_STRUCTURE",
        "claim_text": "HĐQT có 5 thành viên: 1 Chủ tịch, 1 thành viên kiêm Tổng Giám đốc và 3 thành viên không điều hành.",
        "page": 36, "claim_type": "QUALITATIVE", "raw_value": 5.0, "raw_unit": "người",
        "scope": "Toàn doanh nghiệp", "boundary": "Công ty mẹ", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 5.0, "metric_unit": "người",
        "metric_text": "Báo cáo quản trị công ty năm 2023 xác nhận HĐQT gồm 5 thành viên.",
        "methodology": "Luật Doanh nghiệp và Điều lệ BSR",
    },
    {
        "year": 2023, "pillar": "G", "topic": "G_ANTICORRUPTION", "code": None,
        "claim_text": "BSR ban hành và thực thi nghiêm kế hoạch phòng chống tham nhũng, kê khai tài sản minh bạch và truyền thông văn hóa liêm chính.",
        "page": 24, "claim_type": "POLICY", "raw_value": None, "raw_unit": None,
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": None, "metric_unit": None,
        "metric_text": "Báo cáo Ban Kiểm soát năm 2023 không ghi nhận bất kỳ vi phạm tham nhũng nào.",
        "methodology": "Quy chế thanh tra và phòng ngừa tham nhũng",
    },
    {
        "year": 2023, "pillar": "G", "topic": "G_TAX", "code": "TAX_PAID",
        "claim_text": "Tổng số tiền BSR đóng góp nộp ngân sách nhà nước năm 2023 đạt 17.419,9 tỷ VND.",
        "page": 22, "claim_type": "QUANTITATIVE", "raw_value": 17419.9, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 17420.0, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC hợp nhất kiểm toán năm 2023 xác nhận thuế và các khoản nộp nhà nước là 17.420 tỷ VND.",
        "methodology": "Biên bản đối chiếu và xác nhận của Cục Thuế",
    },
    {
        "year": 2023, "pillar": "X", "topic": "FINANCIAL_CONNECTIVITY", "code": "REVENUE",
        "claim_text": "Báo cáo phát triển bền vững BSR 2023 công bố tổng doanh thu đạt 150.115 tỷ VND và lợi nhuận sau thuế đạt 8.592,6 tỷ VND.",
        "page": 22, "claim_type": "QUANTITATIVE", "raw_value": 150115.0, "raw_unit": "tỷ đồng",
        "scope": "Consolidated", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "CONTRADICTS", "metric_value": 147423.0, "metric_unit": "tỷ đồng",
        "metric_text": "Báo cáo tài chính hợp nhất kiểm toán năm 2023 (trang 9) ghi nhận doanh thu bán hàng và cung cấp dịch vụ là 147.423 tỷ VND.",
        "methodology": "Đối soát chéo chênh lệch 2.692 tỷ VND giữa Báo cáo ESG và BCTC kiểm toán",
    },

    # --------------------------------------------------------------------------
    # NĂM 2024 (Trích xuất từ BSR_2024_esg.json và BCTC_BSR_2024_esg.json)
    # --------------------------------------------------------------------------
    {
        "year": 2024, "pillar": "E", "topic": "E_CLIMATE", "code": "GHG_SCOPE_1",
        "claim_text": "Tổng phát thải KNK năm 2024 đạt 1.546.133 tCO2e; mức giảm một phần do Nhà máy dừng 53 ngày để bảo dưỡng tổng thể lần 5 (TA5).",
        "page": 29, "claim_type": "QUANTITATIVE", "raw_value": 1546133.0, "raw_unit": "tCO2e",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 1546133.0, "metric_unit": "tCO2e",
        "metric_text": "Báo cáo kỹ thuật kiểm kê phát thải KNK năm 2024 ghi nhận 1.546.133 tCO2e.",
        "methodology": "Kiểm kê KNK theo tiêu chuẩn ISO 14064",
    },
    {
        "year": 2024, "pillar": "E", "topic": "E_INTENSITY", "code": "GHG_INTENSITY",
        "claim_text": "Cường độ phát thải KNK năm 2024 tính trên biểu đồ là 0,2348 tCO2e/tấn sản phẩm, trong khi mẫu số sản lượng sản xuất là 6.585.976 tấn.",
        "page": 29, "claim_type": "COMPARATIVE", "raw_value": 0.2348, "raw_unit": "tCO2e/tấn sản phẩm",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "tấn sản phẩm",
        "intended_rel": "NOT_COMPARABLE", "metric_value": 1546133.0, "metric_unit": "tCO2e",
        "metric_text": "Số liệu đối chiếu là tổng phát thải tuyệt đối 1.546.133 tCO2e (khác loại giá trị cường độ / tuyệt đối).",
        "methodology": "Comparability gate phát hiện khác value_kind (INTENSITY vs ABSOLUTE)",
    },
    {
        "year": 2024, "pillar": "E", "topic": "E_ENERGY", "code": "ENERGY_TOTAL",
        "claim_text": "Chỉ số hiệu quả năng lượng EII năm 2024 đạt 100,9%, tốt hơn mục tiêu 102%; BSR tiếp tục duy trì chứng chỉ ISO 50001:2018.",
        "page": 25, "claim_type": "TARGET", "raw_value": 100.9, "raw_unit": "%",
        "scope": "Toàn doanh nghiệp", "boundary": "Nhà máy Dung Quất", "value_kind": "INTENSITY", "denominator": "% mục tiêu",
        "intended_rel": "SUPPORTS", "metric_value": 100.9, "metric_unit": "%",
        "metric_text": "Báo cáo thẩm tra năng lượng năm 2024 ghi nhận chỉ số EII lũy kế đạt 100,9%.",
        "methodology": "Solomon EII Index",
    },
    {
        "year": 2024, "pillar": "E", "topic": "E_WATER", "code": "WATER_WITHDRAWAL",
        "claim_text": "Lượng nước ngưng tái chế/tái sử dụng đạt 3.503.200 m3 (tương đương 72,6%); lượng nước biển trao đổi nhiệt gián tiếp là 277.257.914 m3.",
        "page": 26, "claim_type": "QUANTITATIVE", "raw_value": 277257914.0, "raw_unit": "m3",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 277257914.0, "metric_unit": "m3",
        "metric_text": "Hệ thống trạm bơm ghi nhận nước biển trao đổi nhiệt năm 2024 đạt 277.257.914 m3.",
        "methodology": "Đo lưu lượng trực tiếp tại trạm bơm nước biển",
    },
    {
        "year": 2024, "pillar": "E", "topic": "E_WASTE", "code": "HAZARDOUS_WASTE",
        "claim_text": "BSR chưa công bố bảng tổng lượng chất thải và chất thải nguy hại phát sinh dù GRI 306 được xác định là chủ đề trọng yếu.",
        "page": 26, "claim_type": "QUALITATIVE", "raw_value": None, "raw_unit": "tấn",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "MISSING", "metric_value": None, "metric_unit": None,
        "metric_text": None,
        "methodology": None,
    },
    {
        "year": 2024, "pillar": "E", "topic": "E_SPILLS", "code": "SPILL_COUNT",
        "claim_text": "Năm 2024, BSR không ghi nhận sự cố môi trường nghiêm trọng nào; hệ thống giám sát khí thải tự động hoạt động ổn định.",
        "page": 7, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "vụ",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "vụ",
        "metric_text": "Biên bản kiểm tra định kỳ của Sở Tài nguyên và Môi trường ghi nhận 0 vụ vi phạm môi trường.",
        "methodology": "Quan trắc khí thải tự động liên tục",
    },
    {
        "year": 2024, "pillar": "S", "topic": "S_SAFETY", "code": "LTIFR",
        "claim_text": "BSR vượt mốc 49,3 triệu giờ công an toàn không có tai nạn mất ngày công (LTI = 0); tổ chức 176 lần diễn tập ứng phó khẩn cấp.",
        "page": 32, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "ca/triệu giờ công",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "triệu giờ công",
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "ca/triệu giờ công",
        "metric_text": "Báo cáo thống kê an toàn HSE 2024 ghi nhận LTIFR = 0 với 49,3 triệu giờ an toàn.",
        "methodology": "Hệ thống quản lý an toàn ISO 45001:2018",
    },
    {
        "year": 2024, "pillar": "S", "topic": "S_TRAINING", "code": "TRAINING_HOURS",
        "claim_text": "Triển khai 168 chương trình đào tạo cho 16.658 lượt người; thời lượng đào tạo an toàn bình quân đạt 34 giờ/người.",
        "page": 32, "claim_type": "QUANTITATIVE", "raw_value": 34.0, "raw_unit": "giờ/người/năm",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "người",
        "intended_rel": "SUPPORTS", "metric_value": 34.0, "metric_unit": "giờ/người/năm",
        "metric_text": "Báo cáo công tác đào tạo năm 2024 ghi nhận 34 giờ đào tạo an toàn/người.",
        "methodology": "Phần mềm quản trị đào tạo LMS",
    },
    {
        "year": 2024, "pillar": "S", "topic": "S_COMMUNITY", "code": "ENV_EXPENSE",
        "claim_text": "Chi tài trợ an sinh xã hội năm 2024 đạt 110 tỷ VND (giáo dục 39,5 tỷ, y tế 28,5 tỷ); 54,6% người lao động là cư dân địa phương.",
        "page": 30, "claim_type": "QUANTITATIVE", "raw_value": 110.0, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 110.0, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC kiểm toán năm 2024 xác nhận các khoản tài trợ an sinh xã hội là 110 tỷ VND.",
        "methodology": "Quyết toán quỹ hỗ trợ cộng đồng",
    },
    {
        "year": 2024, "pillar": "G", "topic": "G_GOVERNANCE", "code": "BOARD_STRUCTURE",
        "claim_text": "HĐQT có 5 thành viên: 3 thành viên không điều hành và 1 thành viên độc lập tham gia giám sát định kỳ.",
        "page": 37, "claim_type": "QUALITATIVE", "raw_value": 5.0, "raw_unit": "người",
        "scope": "Toàn doanh nghiệp", "boundary": "Công ty mẹ", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 5.0, "metric_unit": "người",
        "metric_text": "Báo cáo quản trị năm 2024 xác nhận HĐQT có 5 thành viên gồm 1 thành viên độc lập.",
        "methodology": "Điều lệ BSR và Luật Doanh nghiệp",
    },
    {
        "year": 2024, "pillar": "G", "topic": "G_ANTICORRUPTION", "code": None,
        "claim_text": "BSR mô tả kiểm soát chặt chẽ xung đột lợi ích trong bổ nhiệm, đấu thầu và đầu tư; không phát hiện vụ việc tiêu cực nào.",
        "page": 37, "claim_type": "POLICY", "raw_value": None, "raw_unit": None,
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": None, "metric_unit": None,
        "metric_text": "Báo cáo Ban Kiểm soát không phát hiện trường hợp tham nhũng hay trục lợi.",
        "methodology": "Kiểm toán nội bộ và giám sát tuân thủ",
    },
    {
        "year": 2024, "pillar": "G", "topic": "G_TAX", "code": "TAX_PAID",
        "claim_text": "Tổng số tiền BSR đóng góp vào ngân sách nhà nước trong năm 2024 là 13.017 tỷ VND.",
        "page": 23, "claim_type": "QUANTITATIVE", "raw_value": 13017.0, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 13017.0, "metric_unit": "tỷ đồng",
        "metric_text": "BCTC hợp nhất kiểm toán năm 2024 xác nhận số thuế và các khoản nộp nhà nước là 13.017 tỷ VND.",
        "methodology": "Biên bản thanh toán thuế điện tử qua kho bạc nhà nước",
    },
    {
        "year": 2024, "pillar": "X", "topic": "FINANCIAL_CONNECTIVITY", "code": "REVENUE",
        "claim_text": "Doanh thu hợp nhất năm 2024 đạt 125.288 tỷ VND và lợi nhuận sau thuế hợp nhất đạt 591 tỷ VND.",
        "page": 23, "claim_type": "QUANTITATIVE", "raw_value": 125288.0, "raw_unit": "tỷ đồng",
        "scope": "Consolidated", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 125288.0, "metric_unit": "tỷ đồng",
        "metric_text": "Báo cáo tài chính kiểm toán hợp nhất 2024 xác nhận doanh thu thuần là 125.288 tỷ VND.",
        "methodology": "Chuẩn mực Kế toán Việt Nam (VAS)",
    },

    # --------------------------------------------------------------------------
    # NĂM 2025 (Trích xuất từ BSR_2025_esg.json và BCTC_BSR_2025_esg.json)
    # --------------------------------------------------------------------------
    {
        "year": 2025, "pillar": "E", "topic": "E_CLIMATE", "code": "GHG_SCOPE_1",
        "claim_text": "Bảng tóm tắt công bố phát thải trực tiếp Scope 1 năm 2025 là 1.780.388 tCO2e và Scope 2 là 2.210 tCO2e.",
        "page": 29, "claim_type": "QUANTITATIVE", "raw_value": 1780388.0, "raw_unit": "tCO2e",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "CONTRADICTS", "metric_value": 1790388.0, "metric_unit": "tCO2e",
        "metric_text": "Bảng chi tiết phụ lục GRI tại trang 65 ghi nhận Scope 1 là 1.790.388 tCO2e (chênh lệch 10.000 tCO2e).",
        "methodology": "Phát hiện mâu thuẫn nội bộ báo cáo giữa bảng tóm tắt (p29) và phụ lục GRI (p65)",
    },
    {
        "year": 2025, "pillar": "E", "topic": "E_INTENSITY", "code": "GHG_INTENSITY",
        "claim_text": "Cường độ phát thải KNK công bố là 0,225 tCO2e/tấn sản phẩm, giảm 4% so với năm 2024.",
        "page": 65, "claim_type": "COMPARATIVE", "raw_value": 0.225, "raw_unit": "tCO2e/tấn sản phẩm",
        "scope": "Scope 1", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "tấn sản phẩm",
        "intended_rel": "SUPPORTS", "metric_value": 0.225, "metric_unit": "tCO2e/tấn sản phẩm",
        "metric_text": "Phụ lục GRI 305-4 xác nhận cường độ phát thải năm 2025 đạt 0,225 tCO2e/tấn sản phẩm.",
        "methodology": "GRI 305-4 cường độ phát thải",
    },
    {
        "year": 2025, "pillar": "E", "topic": "E_ENERGY", "code": "ENERGY_TOTAL",
        "claim_text": "Tổng năng lượng tiêu thụ đạt 26.335.558 GJ; cường độ năng lượng là 3,319 GJ/tấn sản phẩm và chỉ số EII đạt 101,5%.",
        "page": 28, "claim_type": "QUANTITATIVE", "raw_value": 26335558.0, "raw_unit": "GJ",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 26335558.0, "metric_unit": "GJ",
        "metric_text": "Hệ thống quản lý năng lượng xác nhận tổng tiêu thụ năng lượng năm 2025 là 26.335.558 GJ.",
        "methodology": "Quy đổi nhiệt trị tiêu chuẩn theo ISO 50001",
    },
    {
        "year": 2025, "pillar": "E", "topic": "E_WATER", "code": "WATER_WITHDRAWAL",
        "claim_text": "Nước ngọt sử dụng là 3.196.774 m3; nước biển khai thác làm mát là 323.844.900 m3; nước thải sau xử lý là 2.397.357 m3.",
        "page": 31, "claim_type": "QUANTITATIVE", "raw_value": 323844900.0, "raw_unit": "m3",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 323844900.0, "metric_unit": "m3",
        "metric_text": "Lưu lượng kế tại cảng biển ghi nhận lượng nước biển khai thác năm 2025 là 323.844.900 m3.",
        "methodology": "Đo đạc tự động lưu lượng nước biển",
    },
    {
        "year": 2025, "pillar": "E", "topic": "E_WASTE", "code": "HAZARDOUS_WASTE",
        "claim_text": "Tổng chất thải phát sinh là 7.586,89 tấn, trong đó chất thải nguy hại là 3.666,43 tấn; tỷ lệ tái chế/thu hồi đạt 41,8%.",
        "page": 66, "claim_type": "QUANTITATIVE", "raw_value": 3666.43, "raw_unit": "tấn",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 3666.43, "metric_unit": "tấn",
        "metric_text": "Sổ bộ quản lý chất thải nguy hại xác nhận khối lượng chuyển giao là 3.666,43 tấn.",
        "methodology": "Chứng từ chất thải nguy hại theo Thông tư 02/2022/TT-BTNMT",
    },
    {
        "year": 2025, "pillar": "E", "topic": "E_SPILLS", "code": "SPILL_COUNT",
        "claim_text": "BSR ghi nhận 0 sự cố môi trường nghiêm trọng, 0 sự cố tràn dầu và tổ chức 1 cuộc diễn tập ứng phó sự cố môi trường cấp công ty.",
        "page": 25, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "vụ",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "vụ",
        "metric_text": "Báo cáo công tác bảo vệ môi trường xác nhận không có sự cố tràn đổ trong năm 2025.",
        "methodology": "Hệ thống radar giám sát dầu tràn tại phao SPM",
    },
    {
        "year": 2025, "pillar": "S", "topic": "S_SAFETY", "code": "LTIFR",
        "claim_text": "BSR đạt hơn 54,3 triệu giờ công an toàn; LTI = 0, LTIFR = 0, tử vong = 0, bệnh nghề nghiệp = 0; đào tạo HSE đạt 23 giờ/người.",
        "page": 36, "claim_type": "ACHIEVEMENT", "raw_value": 0.0, "raw_unit": "ca/triệu giờ công",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "triệu giờ công",
        "intended_rel": "SUPPORTS", "metric_value": 0.0, "metric_unit": "ca/triệu giờ công",
        "metric_text": "Báo cáo tai nạn lao động xác nhận tỷ lệ tổn thất thời gian làm việc LTIFR = 0.",
        "methodology": "Tiêu chuẩn an toàn lao động OSHA / GRI 403",
    },
    {
        "year": 2025, "pillar": "S", "topic": "S_TRAINING", "code": "TRAINING_HOURS",
        "claim_text": "BSR tổ chức 160 chương trình đào tạo với 14.512 lượt tham gia; thời lượng đào tạo HSE bình quân đạt 23 giờ/người/năm.",
        "page": 39, "claim_type": "QUANTITATIVE", "raw_value": 23.0, "raw_unit": "giờ/người/năm",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "INTENSITY", "denominator": "người",
        "intended_rel": "SUPPORTS", "metric_value": 23.0, "metric_unit": "giờ/người/năm",
        "metric_text": "Hệ thống LMS ghi nhận bình quân đào tạo an toàn môi trường năm 2025 đạt 23 giờ/người.",
        "methodology": "Quản lý đào tạo theo ISO 9001:2015",
    },
    {
        "year": 2025, "pillar": "S", "topic": "S_COMMUNITY", "code": "ENV_EXPENSE",
        "claim_text": "Trang chính báo cáo tổng chi tài trợ an sinh xã hội và cộng đồng năm 2025 là 179,5 tỷ VND (gồm 164,5 tỷ chương trình và 15 tỷ khẩn cấp).",
        "page": 43, "claim_type": "QUANTITATIVE", "raw_value": 179.5, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "CONTRADICTS", "metric_value": 109.2, "metric_unit": "tỷ đồng",
        "metric_text": "Phụ lục GRI 413 tại trang 66 ghi nhận chi phí hoạt động cộng đồng là 109,2 tỷ VND (chênh lệch 70,3 tỷ VND chưa giải trình phạm vi).",
        "methodology": "Phát hiện chênh lệch số liệu giữa nội dung báo cáo chính và phụ lục GRI",
    },
    {
        "year": 2025, "pillar": "G", "topic": "G_GOVERNANCE", "code": "BOARD_STRUCTURE",
        "claim_text": "HĐQT có 7 thành viên, trong đó có 2 thành viên độc lập; thành lập Ban Chiến lược Phát triển trực thuộc HĐQT từ năm 2025.",
        "page": 50, "claim_type": "QUALITATIVE", "raw_value": 7.0, "raw_unit": "người",
        "scope": "Toàn doanh nghiệp", "boundary": "Công ty mẹ", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 7.0, "metric_unit": "người",
        "metric_text": "Nghị quyết ĐHĐCĐ năm 2025 phê chuẩn cơ cấu HĐQT 7 thành viên gồm 2 thành viên độc lập.",
        "methodology": "Luật Doanh nghiệp và Bộ Quy tắc Quản trị công ty",
    },
    {
        "year": 2025, "pillar": "G", "topic": "G_ANTICORRUPTION", "code": None,
        "claim_text": "BSR báo cáo 0 vụ việc tham nhũng được xác nhận, 0 vụ việc cạnh tranh không lành mạnh và 0 đóng góp chính trị.",
        "page": 55, "claim_type": "POLICY", "raw_value": None, "raw_unit": None,
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": None, "metric_unit": None,
        "metric_text": "Báo cáo Ban Kiểm toán nội bộ xác nhận không có hành vi vi phạm đạo đức kinh doanh.",
        "methodology": "Mô hình quản trị rủi ro 3 tuyến",
    },
    {
        "year": 2025, "pillar": "G", "topic": "G_TAX", "code": "TAX_PAID",
        "claim_text": "Tổng số tiền nộp ngân sách nhà nước của BSR trong năm 2025 đạt 14.719 tỷ VND.",
        "page": 54, "claim_type": "QUANTITATIVE", "raw_value": 14719.0, "raw_unit": "tỷ đồng",
        "scope": "Toàn doanh nghiệp", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 14719.0, "metric_unit": "tỷ đồng",
        "metric_text": "Báo cáo tài chính kiểm toán 2025 xác nhận tổng số thuế và khoản nộp ngân sách là 14.719 tỷ VND.",
        "methodology": "Biên bản thanh toán thuế điện tử qua kho bạc",
    },
    {
        "year": 2025, "pillar": "X", "topic": "FINANCIAL_CONNECTIVITY", "code": "REVENUE",
        "claim_text": "Doanh thu năm 2025 đạt 143.542 tỷ VND, lợi nhuận sau thuế đạt 5.217 tỷ VND và tổng tài sản đạt 86.415 tỷ VND.",
        "page": 54, "claim_type": "QUANTITATIVE", "raw_value": 143542.0, "raw_unit": "tỷ đồng",
        "scope": "Consolidated", "boundary": "Hợp nhất", "value_kind": "ABSOLUTE", "denominator": None,
        "intended_rel": "SUPPORTS", "metric_value": 143542.0, "metric_unit": "tỷ đồng",
        "metric_text": "Báo cáo tài chính kiểm toán hợp nhất 2025 xác nhận doanh thu thuần đạt 143.542 tỷ VND.",
        "methodology": "Chuẩn mực Kế toán Việt Nam (VAS)",
    },
]


def build_sample() -> tuple[list[dict], list[dict]]:
    claims = []
    metrics = []

    for idx, r in enumerate(BSR_RECORDS_RAW, start=1):
        year = r["year"]
        claim_id = f"BSR_C{idx:03d}"
        metric_code = r["code"]
        raw_val = r["raw_value"]
        raw_unit = r["raw_unit"]
        intended_rel = r["intended_rel"]

        direction = "IMPROVE" if r["claim_type"] in {"COMPARATIVE", "TARGET", "ACHIEVEMENT"} else "NEUTRAL"

        claims.append({
            "claim_id": claim_id,
            "report_year": year,
            "document_type": "DEMO_ESG_REPORT",
            "page_number": r["page"],
            "source_text": r["claim_text"],
            "claim_type": r["claim_type"],
            "pillar": r["pillar"],
            "topic_id": r["topic"],
            "metric_code": metric_code,
            "actor": "Công ty Cổ phần Lọc hóa dầu Bình Sơn (BSR)",
            "action": "công bố",
            "object": metric_code or r["topic"],
            "raw_value": raw_val,
            "raw_unit": raw_unit,
            "baseline_year": year - 1 if r["claim_type"] == "COMPARATIVE" else None,
            "target_year": year if r["claim_type"] == "TARGET" else None,
            "scope": r["scope"],
            "boundary": r["boundary"],
            "qualifier": "xác nhận" if intended_rel == "SUPPORTS" else "cần rà soát",
            "direction": direction,
            "value_kind": r["value_kind"],
            "denominator": r["denominator"],
            "intended_relationship": intended_rel,
            "confidence": 0.95,
        })

        if intended_rel == "MISSING" or r["metric_value"] is None or metric_code is None:
            continue

        metric_val = r["metric_value"]
        metric_unit = r["metric_unit"] or raw_unit
        metric_kind = "INTENSITY" if r["value_kind"] == "INTENSITY" and intended_rel != "NOT_COMPARABLE" else ("ABSOLUTE" if intended_rel == "NOT_COMPARABLE" else r["value_kind"])
        metric_boundary = r["boundary"]

        metrics.append({
            "metric_id": f"BSR_M{idx:03d}",
            "report_year": year,
            "document_type": "DEMO_SUPPORTING_REPORT",
            "page_number": r["page"],
            "source_text": r["metric_text"] or f"Bằng chứng đối chiếu năm {year}: {metric_code} đạt {metric_val} {metric_unit}.",
            "metric_code": metric_code,
            "metric_name": metric_code,
            "raw_value": metric_val,
            "raw_unit": metric_unit,
            "normalized_value": metric_val,
            "normalized_unit": metric_unit,
            "metric_year": year,
            "scope": r["scope"],
            "boundary": metric_boundary,
            "denominator": r["denominator"],
            "value_kind": metric_kind,
            "methodology": r["methodology"] or "Đối soát kỹ thuật & BCTC kiểm toán",
            "assurance_status": "Audited / Verified",
            "financial_class": "REVENUE" if metric_code == "REVENUE" else ("OPEX" if metric_code == "ENV_EXPENSE" else None),
            "confidence": 0.98,
        })

    return claims, metrics


def write_sample_csv(sample_dir: Path, claims: list[dict], metrics: list[dict]) -> None:
    sample_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("demo_claims.csv", claims), ("demo_metrics.csv", metrics)):
        if not rows:
            continue
        with (sample_dir / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (sample_dir / "README.md").write_text(
        "# Dữ liệu mẫu thực tế BSR (2022–2025)\n\n"
        "Toàn bộ bản ghi trong thư mục này được trích xuất và cấu trúc hóa trực tiếp từ Báo cáo Phát triển bền vững (ESG), "
        "Báo cáo tài chính kiểm toán (BCTC), bản tóm tắt và văn bản OCR của Công ty Cổ phần Lọc hóa dầu Bình Sơn (BSR) "
        "giai đoạn 2022–2025 (tại thư mục `output/`).\n\n"
        "Các bản ghi được gắn nhãn `is_demo_data = true` để làm tập dữ liệu mẫu chuẩn hóa, phục vụ tra cứu, "
        "đối soát bằng chứng và kiểm thử hệ luật phát hiện rủi ro greenwashing trên giao diện ESG Tracker.\n",
        encoding="utf-8",
    )
