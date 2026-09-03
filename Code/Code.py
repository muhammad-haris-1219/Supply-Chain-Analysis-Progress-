import os
import re
from PIL import Image
import pymupdf as fitz
import pyodbc
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

server = r"DESKTOP-GLLJDAK\SQLEXPRESS"
database = "FinancialDataDB"

conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=yes;"
)
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'FinancialRawData')
    BEGIN
        CREATE TABLE FinancialRawData (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            Nature VARCHAR(255) DEFAULT 'FMCG',
            Organization VARCHAR(255),
            [PDF-Year] INT,
            [Statement Type] VARCHAR(255),
            Subsection VARCHAR(255),
            [Item labels] VARCHAR(MAX),
            [Data Year] INT,
            Value VARCHAR(255)
        )
    END
""")
conn.commit()

base_folder = r"D:\WMA\Python\Project\Files"

statement_pattern = re.compile(
    r"^(?:"
    r"(?:CONDENSED\s+)?"
    r"(?:CONSOLIDATED\s+|UNCONSOLIDATED\s+|GROUP\s+)?"
    r"(?:"
    r"STATEMENT\s+OF\s+FINANCIAL\s+POSITION|"
    r"STATEMENT\s+OF\s+PROFIT\s+OR\s+LOSS(?:\s+AND\s+OTHER\s+COMPREHENSIVE\s+INCOME)?|"
    r"STATEMENT\s+OF\s+COMPREHENSIVE\s+INCOME|"
    r"STATEMENT\s+OF\s+CASH\s+FLOWS?|"
    r"STATEMENT\s+OF\s+CHANGES\s+IN\s+EQUITY|"
    r"BALANCE\s+SHEET|"
    r"INCOME\s+STATEMENT|"
    r"PROFIT\s+AND\s+LOSS\s+ACCOUNT(?:\s+AND\s+OTHER\s+COMPREHENSIVE\s+INCOME)?|"
    r"OPERATING\s+AND\s+FINANCIAL\s+HIGHLIGHTS|"
    r"FINANCIAL\s+HIGHLIGHTS|"
    r"OPERATING\s+HIGHLIGHTS|"
    r"FINANCIAL\s+PERFORMANCE\s+AT\s+A\s+GLANCE|"
    r"FINANCIAL\s+SUMMARY|"
    r"PERFORMANCE\s+INDICATORS|"
    r"KEY\s+OPERATING\s+AND\s+FINANCIAL\s+DATA|"
    r"OPERATING\s+PERFORMANCE|"
    r"FINANCIAL\s+PERFORMANCE|"
    r"SUMMARY\s+OF\s+PROFIT\s+OR\s+LOSS|"
    r"FINANCIAL\s+STATEMENTS?"
    r")"
    r")$",
    re.IGNORECASE,
)

year_extractor = re.compile(r"\b(20\d{2})\b")
financial_num_pattern = re.compile(
    r"^\s*(?:"
    r"\(\s*\$?\s*-?\s*\d[\d,]*(?:\.\d+)?\s*\)"
    r"|"
    r"-\s*\$?\s*\d[\d,]*(?:\.\d+)?"
    r"|"
    r"\$?\s*\d[\d,]*(?:\.\d+)?"
    r")\s*$"
)

KNOWN_SUBSECTIONS = {
    "ASSETS",
    "NON CURRENT ASSETS",
    "CURRENT ASSETS",
    "EQUITY",
    "SHAREHOLDERS EQUITY",
    "LIABILITIES",
    "NON CURRENT LIABILITIES",
    "CURRENT LIABILITIES",
    "REVENUE",
    "EXPENSES",
    "OPERATING EXPENSES",
    "COST OF SALES",
    "OPERATING ACTIVITIES",
    "INVESTING ACTIVITIES",
    "FINANCING ACTIVITIES",
    "CASH FLOWS",
}

STANDARD_LABELS = [
    "Cost of sales",
    "Gross profit",
    "Administrative expenses",
    "Selling and distribution expenses",
    "Operating profit",
    "Finance cost",
    "Profit before tax",
    "Taxation",
    "Profit after tax",
    "Revenue from contracts with customers",
    "Other income",
    "Other expenses",
    "Net profit",
    "Property, plant and equipment",
    "Intangible assets",
    "Right-of-use assets",
    "Long term investments",
    "Deferred tax asset",
    "Current assets",
    "Inventories",
    "Trade debts",
    "Advances, deposits and prepayments",
    "Cash and bank balances",
    "Total assets",
    "Share capital",
    "Reserves",
    "Unappropriated profit",
    "Total equity",
    "Non-current liabilities",
    "Long term financing",
    "Lease liabilities",
    "Current liabilities",
    "Trade and other payables",
    "Short term borrowings",
    "Total equity and liabilities",
    "Net sales",
    "Stores and spares",
    "Stock in trade",
    "Loans and advances",
    "Other receivables",
    "Tax refunds due from Government",
    "Issued, subscribed and paid up capital",
    "Deferred liabilities",
    "Accrued mark-up",
    "Current portion of long term financing",
    "Unclaimed dividend",
    "Provision for taxation",
    "Contingencies and commitments",
    "Gross margin",
    "Operating margin",
    "Disaggregation of revenue",
    "Local sales",
    "Export sales",
    "Sales returns, discounts and direct expense",
    "Add: Export rebate",
    "Sales tax",
    "Share of profit from associated companies - net",
    "Profit before taxation",
    "Profit for the year",
    "Operating fixed assets",
]

for root, dirs, files in os.walk(base_folder):
    for filename in files:
        if not filename.lower().endswith(".pdf"):
            continue

        name_part, _ = os.path.splitext(filename)
        found_filename_years = [int(y) for y in year_extractor.findall(name_part)]
        file_pdf_year = max(found_filename_years) if found_filename_years else None

        clean_org = re.sub(r"\b(20\d{2})\b", "", name_part, flags=re.IGNORECASE)
        clean_org = re.sub(r"[-_]", " ", clean_org).strip().upper()
        clean_org = re.sub(r"\s+", " ", clean_org)
        if not clean_org:
            clean_org = "UNKNOWN"

        file_path = os.path.join(root, filename)
        doc = fitz.open(file_path)

        active_statement = None
        current_subsection = ""
        pending_label_prefix = ""
        previous_column_boundaries = []
        previous_year_header_count = 0

        for page_num in range(len(doc)):
            page = doc[page_num]

            native_words = page.get_text("words")
            words = []

            if native_words and len(native_words) >= 10:
                words = native_words
            else:
                mat = page.derotation_matrix * fitz.Matrix(150 / 72.0, 150 / 72.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                ocr_data = pytesseract.image_to_data(
                    img,
                    output_type=pytesseract.Output.DICT,
                    config=r"--oem 3 --psm 3 -c preserve_interword_spaces=1",
                )

                ocr_w, ocr_h = pix.width, pix.height
                page_w, page_h = page.rect.width, page.rect.height
                scale_x = page_w / max(ocr_w, 1)
                scale_y = page_h / max(ocr_h, 1)

                for i in range(len(ocr_data["text"])):
                    t = ocr_data["text"][i].strip()

                    try:
                        c = float(ocr_data["conf"][i])
                    except (ValueError, TypeError):
                        continue

                    if t and len(t) >= 1 and c > 25.0:
                        lx0, ly0, lw, lh = (
                            ocr_data["left"][i],
                            ocr_data["top"][i],
                            ocr_data["width"][i],
                            ocr_data["height"][i],
                        )
                        rx0, ry0 = lx0 * scale_x, ly0 * scale_y
                        rx1, ry1 = (lx0 + lw) * scale_x, (ly0 + lh) * scale_y

                        words.append((rx0, ry0, rx1, ry1, t))

            if not words:
                continue

            rect = page.rect
            page_height = rect.height

            rows_by_y = {}

            for w in words:
                x0, y0, x1, y1, word_str = w[:5]

                if y1 > page_height * 0.96:
                    continue

                text = str(word_str).strip()

                if not text:
                    continue

                center_y = (y0 + y1) / 2
                best_row = None
                best_distance = float("inf")

                for stored_y in rows_by_y:
                    distance = abs(stored_y - center_y)

                    if distance <= 4 and distance < best_distance:
                        best_distance = distance
                        best_row = stored_y

                if best_row is None:
                    rows_by_y[center_y] = [(x0, y0, x1, y1, text)]
                else:
                    rows_by_y[best_row].append((x0, y0, x1, y1, text))

            sorted_y_keys = sorted(rows_by_y.keys())

            for y_key in sorted_y_keys:
                rows_by_y[y_key].sort(key=lambda x: x[0])

            detected_years_by_x = {}
            year_candidates = []

            for i, y_key in enumerate(sorted_y_keys):
                row_words = rows_by_y[y_key]
                row_years = []

                for w in row_words:
                    token = w[4].strip()

                    if year_extractor.fullmatch(token):
                        year_value = int(token)

                        if 2000 <= year_value <= 2100:
                            row_years.append({
                                "year": year_value,
                                "x": (w[0] + w[2]) / 2,
                            })

                if not row_years:
                    continue

                following_numeric_rows = 0

                for next_y in sorted_y_keys[i + 1 : i + 4]:
                    next_words = rows_by_y[next_y]
                    numeric_count = 0

                    for nw in next_words:
                        nt = nw[4].strip().replace(" ", "")

                        if financial_num_pattern.fullmatch(nt):
                            numeric_count += 1

                    if numeric_count > 0:
                        following_numeric_rows += 1

                if following_numeric_rows > 0:
                    year_candidates.append({
                        "years": row_years,
                        "score": (len(row_years) * 10)
                        + (following_numeric_rows * 5),
                    })

            if year_candidates:
                best_year_group = max(year_candidates, key=lambda x: x["score"])

                for item in best_year_group["years"]:
                    x_key = item["x"]
                    detected_years_by_x[x_key] = item["year"]

            year_headers = [
                {"year": year_value, "x": x_key}
                for x_key, year_value in sorted(
                    detected_years_by_x.items(), key=lambda item: item[0]
                )
            ]

            column_boundaries = []

            if len(year_headers) == 1:
                column_boundaries.append((0, rect.width, year_headers[0]["year"]))

            elif len(year_headers) >= 2:
                for i in range(len(year_headers)):
                    current_x = year_headers[i]["x"]
                    current_year = year_headers[i]["year"]

                    if i == 0:
                        next_x = year_headers[i + 1]["x"]
                        left_x = 0
                        right_x = (current_x + next_x) / 2

                    elif i == len(year_headers) - 1:
                        previous_x = year_headers[i - 1]["x"]
                        left_x = (previous_x + current_x) / 2
                        right_x = rect.width

                    else:
                        previous_x = year_headers[i - 1]["x"]
                        next_x = year_headers[i + 1]["x"]
                        left_x = (previous_x + current_x) / 2
                        right_x = (current_x + next_x) / 2

                    column_boundaries.append((left_x, right_x, current_year))

            if column_boundaries:
                previous_column_boundaries = column_boundaries.copy()
                previous_year_header_count = len(year_headers)
            elif previous_column_boundaries:
                if previous_year_header_count >= 2:
                    column_boundaries = previous_column_boundaries.copy()
                else:
                    column_boundaries = []
            else:
                column_boundaries = []

            records_to_insert = []

            for y_key in sorted_y_keys:
                row_words = rows_by_y[y_key]
                tokens = [w[4].strip() for w in row_words if w[4].strip()]

                if not tokens:
                    continue

                full_row_str = " ".join(tokens).strip()
                full_row_upper = full_row_str.upper()

                statement_type = None

                if statement_pattern.fullmatch(full_row_upper.strip()):
                    if re.search(
                        r"\bSTATEMENT\s+OF\s+FINANCIAL\s+POSITION\b|\bBALANCE\s+SHEET\b",
                        full_row_upper,
                    ):
                        statement_type = "STATEMENT OF FINANCIAL POSITION"
                    elif re.search(
                        r"\bSTATEMENT\s+OF\s+PROFIT\s+OR\s+LOSS\b|\bINCOME\s+STATEMENT\b|\bPROFIT\s+AND\s+LOSS\s+ACCOUNT\b",
                        full_row_upper,
                    ):
                        statement_type = "STATEMENT OF PROFIT OR LOSS"
                    elif re.search(
                        r"\bSTATEMENT\s+OF\s+COMPREHENSIVE\s+INCOME\b",
                        full_row_upper,
                    ):
                        statement_type = "STATEMENT OF COMPREHENSIVE INCOME"
                    elif re.search(
                        r"\bSTATEMENT\s+OF\s+CASH\s+FLOWS?\b", full_row_upper
                    ):
                        statement_type = "STATEMENT OF CASH FLOWS"
                    elif re.search(
                        r"\bSTATEMENT\s+OF\s+CHANGES\s+IN\s+EQUITY\b",
                        full_row_upper,
                    ):
                        statement_type = "STATEMENT OF CHANGES IN EQUITY"
                    elif re.search(
                        r"\bOPERATING\s+AND\s+FINANCIAL\s+HIGHLIGHTS\b",
                        full_row_upper,
                    ):
                        statement_type = "OPERATING AND FINANCIAL HIGHLIGHTS"
                    elif re.search(
                        r"\bFINANCIAL\s+PERFORMANCE\s+AT\s+A\s+GLANCE\b",
                        full_row_upper,
                    ):
                        statement_type = "FINANCIAL PERFORMANCE AT A GLANCE"
                    elif re.search(
                        r"\bFINANCIAL\s+HIGHLIGHTS\b", full_row_upper
                    ):
                        statement_type = "FINANCIAL HIGHLIGHTS"
                    elif re.search(r"\bOPERATING\s+HIGHLIGHTS\b", full_row_upper):
                        statement_type = "OPERATING HIGHLIGHTS"
                    elif re.search(
                        r"\bOPERATING\s+PERFORMANCE\b", full_row_upper
                    ):
                        statement_type = "OPERATING PERFORMANCE"
                    elif re.search(
                        r"\bFINANCIAL\s+PERFORMANCE\b", full_row_upper
                    ):
                        statement_type = "FINANCIAL PERFORMANCE"
                    elif re.search(r"\bFINANCIAL\s+SUMMARY\b", full_row_upper):
                        statement_type = "FINANCIAL SUMMARY"
                    elif re.search(
                        r"\bPERFORMANCE\s+INDICATORS\b", full_row_upper
                    ):
                        statement_type = "PERFORMANCE INDICATORS"
                    elif re.search(
                        r"\bKEY\s+OPERATING\s+AND\s+FINANCIAL\s+DATA\b",
                        full_row_upper,
                    ):
                        statement_type = "KEY OPERATING AND FINANCIAL DATA"
                    elif re.search(
                        r"\bSUMMARY\s+OF\s+PROFIT\s+OR\s+LOSS\b", full_row_upper
                    ):
                        statement_type = "SUMMARY OF PROFIT OR LOSS"
                    elif re.search(
                        r"\bFINANCIAL\s+STATEMENTS?\b", full_row_upper
                    ):
                        statement_type = "FINANCIAL STATEMENTS"

                if statement_type:
                    active_statement = statement_type
                    current_subsection = ""
                    pending_label_prefix = ""
                    continue

                numeric_words = []

                for w in row_words:
                    token = w[4].strip()
                    clean_token = token.replace(" ", "")

                    if financial_num_pattern.fullmatch(clean_token):
                        if not year_extractor.fullmatch(clean_token):
                            numeric_words.append(w)

                if not numeric_words:
                    if re.search(r"\b20\d{2}\b", full_row_str):
                        continue

                    if re.search(
                        r"^(NOTE|NOTES|RUPEES|AMOUNTS?|RESTATED|PAGE|CONTENTS|INDEX)\b",
                        full_row_upper,
                    ):
                        continue

                    label_check = re.sub(r"\s+", "", full_row_str.lower())
                    is_known_label = False

                    for standard_label in STANDARD_LABELS:
                        standard_check = re.sub(
                            r"\s+", "", standard_label.lower()
                        )
                        if label_check == standard_check:
                            is_known_label = True
                            break

                    normalized_row = re.sub(
                        r"[- ]+", " ", full_row_upper
                    ).strip()

                    if normalized_row in KNOWN_SUBSECTIONS:
                        current_subsection = normalized_row[:250]
                        pending_label_prefix = ""
                        continue

                    if (
                        not is_known_label
                        and len(tokens) <= 6
                        and len(full_row_str) <= 100
                        and not full_row_str.isupper()
                        and not re.search(r"[.!?;:]$", full_row_str)
                        and not re.search(
                            r"^(NOTE|NOTES|RUPEES|AMOUNTS?|RESTATED|PAGE|CONTENTS|INDEX)\b",
                            full_row_upper,
                        )
                    ):
                        if pending_label_prefix:
                            pending_label_prefix = (
                                pending_label_prefix + " " + full_row_str
                            )
                        else:
                            pending_label_prefix = full_row_str

                    continue

                label_tokens = []
                numeric_values = []
                found_first_number = False

                for w in row_words:
                    token = w[4].strip()
                    clean_token = token.replace(" ", "")

                    is_number = bool(
                        financial_num_pattern.fullmatch(clean_token)
                        and not year_extractor.fullmatch(clean_token)
                    )

                    if is_number:
                        found_first_number = True
                        numeric_values.append(w)
                    elif not found_first_number:
                        label_tokens.append(token)

                raw_label = " ".join(label_tokens).strip()

                if pending_label_prefix:
                    if raw_label:
                        raw_label = pending_label_prefix + " " + raw_label
                    else:
                        raw_label = pending_label_prefix
                    pending_label_prefix = ""

                line_item_label = re.sub(r"^\d+[\.\)]\s*", "", raw_label)
                line_item_label = re.sub(r"\s+", " ", line_item_label).strip()

                if not line_item_label:
                    continue

                if not re.search(r"[A-Za-z]", line_item_label):
                    continue

                if len(line_item_label) > 250:
                    continue

                clean_raw_label = re.sub(
                    r"[^a-z0-9]", "", line_item_label.lower()
                )

                for standard_label in STANDARD_LABELS:
                    clean_std = re.sub(r"[^a-z0-9]", "", standard_label.lower())
                    if clean_raw_label == clean_std:
                        line_item_label = standard_label
                        break

                for number_word in numeric_values:
                    value = number_word[4].strip()

                    if not value:
                        continue

                    if not re.search(r"\d", value):
                        continue

                    value_x = (number_word[0] + number_word[2]) / 2
                    data_year = None

                    for left_x, right_x, header_year in column_boundaries:
                        if left_x <= value_x <= right_x + 2:
                            data_year = header_year
                            break

                    if data_year is None:
                        continue

                    records_to_insert.append((
                        "FMCG",
                        clean_org[:250],
                        file_pdf_year,
                        active_statement,
                        current_subsection,
                        line_item_label,
                        int(data_year),
                        value[:250],
                    ))

            if records_to_insert:
                insert_sql = """
                    INSERT INTO FinancialRawData 
                    (Nature, Organization, [PDF-Year], [Statement Type], Subsection, [Item labels], [Data Year], Value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.setinputsizes([
                    (pyodbc.SQL_VARCHAR, 255),
                    (pyodbc.SQL_VARCHAR, 255),
                    None,
                    (pyodbc.SQL_VARCHAR, 255),
                    (pyodbc.SQL_VARCHAR, 255),
                    (pyodbc.SQL_VARCHAR, 8000),
                    None,
                    (pyodbc.SQL_VARCHAR, 255),
                ])
                cursor.fast_executemany = True
                cursor.executemany(insert_sql, records_to_insert)
                conn.commit()

        doc.close()

cursor.close()
conn.close()