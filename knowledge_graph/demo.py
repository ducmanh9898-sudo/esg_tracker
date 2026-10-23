import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "extract" / "esg"


def load_report(year: int) -> dict:
    """Đọc dữ liệu ESG của BSR theo năm."""
    file_path = DATA_DIR / f"BSR_{year}_esg.json"

    with file_path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


# Đọc báo cáo BSR trong ba năm.
reports = {}

for year in [2023, 2024, 2025]:
    reports[year] = load_report(year)
    print(f"Đã đọc dữ liệu BSR năm {year}")


# Lấy hai giá trị Scope 1 năm 2025 từ hai vị trí trong báo cáo.
climate_2025 = reports[2025]["environment"]["climate_and_ghg"]

primary_value = next(
    item["value"]
    for item in climate_2025["scope_1_tCO2e_series_primary"]
    if item["year"] == 2025
)

alternative_value = climate_2025[
    "appendix_alternative_2025_values"
]["scope_1_tCO2e"]

difference = abs(primary_value - alternative_value)


print("\nKIỂM TRA SCOPE 1 NĂM 2025")
print(f"Giá trị chính:   {primary_value:,.0f} tCO2e")
print(f"Giá trị phụ lục: {alternative_value:,.0f} tCO2e")
print(f"Chênh lệch:      {difference:,.0f} tCO2e")

if difference > 0:
    print("Kết quả: Phát hiện hai giá trị không nhất quán.")
else:
    print("Kết quả: Hai giá trị nhất quán.")