"""Author the explicit, reviewable mapping; not an automatic ESG extractor."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
items = []


def add(year, pointer, metric, label, dimension, topic, unit, pages, period=None,
        scope="company_reported", kind="reported_measurement", variant="reported", **extra):
    items.append(dict(selection_id=f"C{len(items)+1:02}", company_id="BSR",
        source_path=f"esg/BSR_{year}_esg.json", source_pointer=pointer,
        metric_id=metric, label=label, dimension=dimension, topic=topic,
        unit=unit, source_pages=pages, observation_year=period or year,
        scope=scope, claim_type=kind, variant=variant, **extra))


add(2023,"/environment/climate_and_ghg/production_and_total_emissions_series/2/ghg_tCO2e","ghg_total_unspecified","Tổng phát thải KNK", "E","climate","tCO2e",[30],scope="ghg_scope_unspecified")
add(2023,"/social/workforce/gender_percent/female","female_share","Tỷ lệ lao động nữ","S","workforce","percent",[32],scope="reported_workforce")
add(2023,"/social/workforce/gender_percent/male","male_share","Tỷ lệ lao động nam","S","workforce","percent",[32],scope="reported_workforce")
add(2023,"/governance/board_and_sustainability_oversight/board_members","board_total","Số thành viên HĐQT","G","board","person",[36],scope="board")
add(2023,"/governance/board_and_sustainability_oversight/chair_CEO_separation","chair_ceo_separate","Tách Chủ tịch và Tổng giám đốc","G","board","boolean",[36],scope="board",kind="governance_statement")
add(2023,"/environment/headline_metrics/0/value","eii","Chỉ số cường độ năng lượng EII","E","energy","percent",[25],scope="refinery_eii")
add(2023,"/environment/headline_metrics/0/target_value","eii","Mục tiêu EII","E","energy","percent",[25],scope="refinery_eii",kind="target",variant="target",direction="lower_is_better")
add(2023,"/environment/headline_metrics/3/value","freshwater_use","Nước ngọt sử dụng","E","water","m3",[26],scope="freshwater")
add(2024,"/environment/climate_and_ghg/0/series/2/ghg_tCO2e","ghg_total_unspecified","Tổng KNK 2023 trình bày lại năm 2024","E","climate","tCO2e",[29],period=2023,scope="ghg_scope_unspecified",variant="historical_comparator")
add(2024,"/environment/climate_and_ghg/0/series/3/ghg_tCO2e","ghg_total_unspecified","Tổng phát thải KNK","E","climate","tCO2e",[29],scope="ghg_scope_unspecified")
add(2024,"/governance/board_and_sustainability_oversight/0/metrics/board_members","board_total","Số thành viên HĐQT","G","board","person",[37],scope="board")
add(2024,"/governance/board_and_sustainability_oversight/0/metrics/independent_board_members","board_independent","Thành viên HĐQT độc lập","G","board","person",[37],scope="board")
add(2024,"/social/workforce_and_local_presence/0/value","employees_total","Tổng lao động","S","workforce","person",[31,33],scope="reported_workforce")
add(2024,"/environment/climate_and_ghg/4/phase_1_MWp","solar_capacity","Điện mặt trời giai đoạn 1 dự kiến","E","energy","MWp",[41],scope="planned_solar_phase_1",kind="planned_capacity",realization="planned")
add(2025,"/environment/climate_and_ghg/scope_1_tCO2e_series_primary/3/value","ghg_scope1","Scope 1 tại chuỗi số liệu chính","E","climate","tCO2e",[29,65],scope="scope1",variant="primary")
add(2025,"/environment/climate_and_ghg/appendix_alternative_2025_values/scope_1_tCO2e","ghg_scope1","Scope 1 tại bảng phụ lục khác","E","climate","tCO2e",[65],scope="scope1",variant="appendix_alternative")
add(2025,"/environment/climate_and_ghg/scope_2_tCO2e_series/3/value","ghg_scope2","Phát thải Scope 2","E","climate","tCO2e",[65],scope="scope2")
add(2025,"/environment/climate_and_ghg/intensity_kgCO2e_per_tonne_product_series/2/value","ghg_intensity","Cường độ KNK năm 2024 trong báo cáo 2025","E","climate","kgCO2e/t_product",[29,65],period=2024,scope="reported_product_intensity")
add(2025,"/environment/climate_and_ghg/intensity_kgCO2e_per_tonne_product_series/3/value","ghg_intensity","Cường độ KNK năm 2025","E","climate","kgCO2e/t_product",[29,65],scope="reported_product_intensity")
add(2025,"/environment/headline_metrics/3/value","ghg_intensity_reduction","Mức giảm cường độ KNK so với 2024","E","climate","percent",[13,29],scope="reported_product_intensity",kind="quantitative_change")
add(2025,"/social/workforce/total_employees","employees_total","Tổng lao động","S","workforce","person",[39,66],scope="reported_workforce")
add(2025,"/social/workforce/male_employees_reported","employees_male","Lao động nam","S","workforce","person",[39,66],scope="reported_workforce")
add(2025,"/social/workforce/female_employees_reported","employees_female","Lao động nữ","S","workforce","person",[39,66],scope="reported_workforce")
add(2025,"/environment/waste_and_circularity/2025/total_waste_tonnes","waste_total","Tổng chất thải","E","waste","tonne",[31,65],scope="reported_waste")
add(2025,"/environment/waste_and_circularity/2025/hazardous_waste_tonnes","waste_hazardous","Chất thải nguy hại","E","waste","tonne",[65],scope="reported_waste")
add(2025,"/environment/waste_and_circularity/2025/non_hazardous_waste_tonnes","waste_nonhazardous","Chất thải không nguy hại","E","waste","tonne",[65],scope="reported_waste")
add(2025,"/environment/waste_and_circularity/2025/recycled_or_reused_tonnes","waste_recycled","Chất thải tái chế / tái sử dụng","E","waste","tonne",[31,65],scope="reported_waste")
add(2025,"/environment/waste_and_circularity/2025/landfill_or_final_treatment_tonnes","waste_other_treatment","Chất thải chôn lấp / xử lý cuối","E","waste","tonne",[31,65],scope="reported_waste")
add(2025,"/governance/board_and_sustainability_oversight/board_members","board_total","Số thành viên HĐQT","G","board","person",[50,51,66],scope="board")
add(2025,"/governance/board_and_sustainability_oversight/independent_board_members","board_independent","Thành viên HĐQT độc lập","G","board","person",[50,51,66],scope="board")

rules = [
 dict(id="R01",name="Hai giá trị cùng chỉ tiêu, kỳ và báo cáo",kind="same_report_conflict",metrics=["ghg_scope1"],tolerance=1,unit="tCO2e",failure="Contradicted",basis="Project arithmetic consistency; không phải kết luận vi phạm GRI",guard="Cùng company/report/period/metric/unit/scope; không bỏ giá trị alternative."),
 dict(id="R02",name="Đối soát tổng và các thành phần",kind="sum_parts",total="employees_total",parts=["employees_male","employees_female"],report_year=2025,tolerance=0,unit="person",failure="NeedsReview",basis="Project reconciliation",guard="Các phần cùng kỳ/phạm vi/đơn vị. Chưa xác minh danh mục là đầy đủ nên chênh lệch chỉ là NeedsReview."),
 dict(id="R03",name="Đối soát phân loại chất thải",kind="sum_parts",total="waste_total",parts=["waste_hazardous","waste_nonhazardous"],report_year=2025,tolerance=0.02,unit="tonne",failure="NeedsReview",basis="Project reconciliation; sai số làm tròn ba số 2 chữ số thập phân <= 0.015 tấn",guard="Không ép các nhóm là đầy đủ khi chưa kiểm tra PDF gốc."),
 dict(id="R04",name="Đối soát phương thức xử lý chất thải",kind="sum_parts",total="waste_total",parts=["waste_recycled","waste_other_treatment"],report_year=2025,tolerance=0.02,unit="tonne",failure="NeedsReview",basis="Project reconciliation",guard="Supported chỉ nghĩa là phép cộng trong tập số liệu khớp."),
 dict(id="R05",name="Cùng năm đo, khác năm báo cáo",kind="cross_report_revision",metrics=["ghg_total_unspecified"],tolerance=1,unit="tCO2e",failure="NeedsReview",basis="Project temporal consistency",guard="Không kết luận gian lận: có thể do restatement hoặc thay đổi boundary/method chưa được trích."),
 dict(id="R06",name="Thành viên độc lập không vượt tổng HĐQT",kind="subset",total="board_total",part="board_independent",tolerance=0,unit="person",failure="Contradicted",basis="Project set cardinality",guard="Thiếu part -> InsufficientEvidence, không tự gán 0; không kiểm tra tỷ lệ tối thiểu theo luật."),
 dict(id="R07",name="Đối chiếu phần trăm giảm được công bố",kind="percent_change",metric="ghg_intensity",claim_metric="ghg_intensity_reduction",report_year=2025,from_year=2024,to_year=2025,tolerance=0.5,unit="kgCO2e/t_product",failure="NeedsReview",basis="Project arithmetic; số giảm công bố được làm tròn đến phần trăm nguyên",guard="Dùng hai năm từ cùng báo cáo; kiểm tra mẫu số > 0; không so cường độ với phát thải tuyệt đối."),
 dict(id="R08",name="Đối chiếu EII với mục tiêu cùng kỳ",kind="target",metric="eii",report_year=2023,tolerance=0,unit="percent",direction="lower_is_better",failure="NeedsReview",basis="Project target comparison; lower-is-better được ghi trong nguồn trích",guard="Không dùng kế hoạch làm kết quả thực hiện; chỉ chạy khi có actual và target cùng kỳ/phạm vi."),
 dict(id="R09",name="Tổng tỷ lệ nam và nữ",kind="sum_constant",metrics=["female_share","male_share"],report_year=2023,expected=100,tolerance=0.1,unit="percent",failure="NeedsReview",basis="Project arithmetic; hai tỷ lệ hiển thị một chữ số thập phân",guard="Chỉ kiểm tra tổng tỷ lệ đã chọn, không suy diễn số đếm."),
]
for name, value in [("selection.json",items),("rules.json",rules)]:
    (ROOT/'data'/'config'/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Explicit alias crosswalk for overlapping extracts of the SAME PVD 2025 PDF.
pairs = [
 ("ghg_scope1","tCO2e","/environment/ghg_emissions/scope_1_tco2e","/environment/ghg_emissions/scope_1_tco2e"),
 ("ghg_scope2","tCO2e","/environment/ghg_emissions/scope_2_tco2e","/environment/ghg_emissions/scope_2_tco2e"),
 ("waste_total","tonne","/environment/waste/total_waste_tonnes","/environment/waste_and_spills/total_waste_tonnes"),
 ("employees_total","person","/social/workforce/total_employees","/social/labor_relations_and_training/total_employees"),
 ("board_total","person","/governance/board/members","/governance/board/board_members"),
 ("board_independent","person","/governance/board/independent_members","/governance/board/independent_board_members"),
 ("training_cost","billion_VND","/social/training/training_cost_billion_vnd","/social/labor_relations_and_training/training_cost_billion_vnd"),
 ("contractor_fatalities","person","/social/health_and_safety/contractor_fatalities","/social/occupational_health_and_safety/contractor_fatalities"),
 ("health_insurance_contribution","billion_VND","/social/labor_benefits_and_parental_leave/health_insurance_contribution_billion_vnd","/social/labor_relations_and_training/employee_health_insurance_contributions_billion_vnd"),
]
(ROOT/'data/config/pvd_aliases.json').write_text(json.dumps(pairs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Wrote',len(items),'claim mappings and',len(rules),'rules')
