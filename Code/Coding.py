import os
import re
import pymupdf as fitz
import pyodbc
import difflib
import pytesseract


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

server = r"DESKTOP-GLLJDAK\SQLEXPRESS"
database = "FinancialDataDB"

conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
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
    r"^\s*"
    r"(?:(?:CONSOLIDATED|CONDENSED|INTERIM|UNAUDITED|GROUP|STANDALONE|SEPARATE|UNCONSOLIDATED|NOTES?(?:\s+TO\s+(?:THE)?)?)\s+)*"
    r"(?:STATEMENT\s+OF\s+FINANCIAL\s+POSITION|"
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
    r"NOTES?\s+(?:TO\s+THE\s+)?CONSOLIDATED|"
    r"NOTES?\s+(?:TO\s+THE\s+)?UNCONSOLIDATED|"
    r"REPORTABLE\s+SEGMENTS?|"
    r"REPORTABLE\s+SEGEMENTS?|"
    r"UNCONSOLIDATED\s+STATEMENT\s+OF|"
    r"FINANCIAL\s+SUMMARY|"
    r"PERFORMANCE\s+INDICATORS|"
    r"SUMMARY\s+OF\s+PROFIT\s+OR\s+LOSS|"
    r"KEY\s+OPERATING\s+AND\s+FINANCIAL\s+DATA|"
    r"FINANCIAL\s+STATEMENTS?)"
    r"\s*$",
    re.IGNORECASE
)

year_extractor = re.compile(r"\b(20\d{2})\b")
financial_num_pattern = re.compile(r"^[\(\$-]?\s*\d{1,3}(,\d{3})+(\.\d+)?\s*\)?$|^[\(\$-]?\s*\d{4,}(\.\d+)?\s*\)?$|^[\(\$-]?\s*\d{1,3}\s*\)?$")

STANDARD_LABELS = [
    "Cost of sales", "Gross profit", "Administrative expenses", "Selling and distribution expenses",
    "Operating profit", "Finance cost", "Profit before tax", "Taxation", "Profit after tax",
    "Revenue from contracts with customers", "Other income", "Other expenses", "Net profit",
    "Property, plant and equipment", "Intangible assets", "Right-of-use assets", "Long term investments",
    "Deferred tax asset", "Current assets", "Inventories", "Trade debts", "Advances, deposits and prepayments",
    "Cash and bank balances", "Total assets", "Share capital", "Reserves", "Unappropriated profit",
    "Total equity", "Non-current liabilities", "Long term financing", "Lease liabilities",
    "Current liabilities", "Trade and other payables", "Short term borrowings", "Total equity and liabilities",
    "Net sales", "Stores and spares", "Stock in trade", "Loans and advances", "Other receivables",
    "Tax refunds due from Government", "Issued, subscribed and paid up capital", "Deferred liabilities",
    "Accrued mark-up", "Current portion of long term financing", "Unclaimed dividend", "Provision for taxation",
    "Contingencies and commitments", "Gross margin", "Operating margin", "Disaggregation of revenue",
    "Local sales", "Export sales", "Sales returns, discounts and direct expense", "Add: Export rebate",
    "Sales tax", "Share of profit from associated companies - net", "Profit before taxation", "Profit for the year", "Operating fixed assets"
]

def clean_year_string(val):
    cleaned = re.sub(r'\D', '', str(val))
    return int(cleaned) if cleaned else 2026

def clean_item_label(label):
    label = re.sub(r'^\d+[\.\)]\s*', '', label)
    words = label.split()
    if words and sum(1 for w in words if len(w) == 1) > len(words) / 2:
        label = "".join(words)
    label = re.sub(r'\s+', ' ', label).strip()
    
    label_no_space = label.replace(" ", "").lower()
    for std in STANDARD_LABELS:
        if std.replace(" ", "").lower() == label_no_space:
            return std

    matches = difflib.get_close_matches(label, STANDARD_LABELS, n=1, cutoff=0.75)
    if matches:
        return matches[0]
            
    return label

for root, dirs, files in os.walk(base_folder):
    for filename in files:
        if not filename.lower().endswith(".pdf"):
            continue

        name_part, _ = os.path.splitext(filename)
        found_filename_years = [clean_year_string(y) for y in year_extractor.findall(name_part)]
        file_pdf_year = max(found_filename_years) if found_filename_years else 2026

        clean_org = re.sub(r"\b(20\d{2})\b", "", name_part, flags=re.IGNORECASE)
        clean_org = re.sub(r'[-_]', ' ', clean_org).strip().upper()
        clean_org = re.sub(r'\s+', ' ', clean_org)
        if not clean_org:
            clean_org = "UNKNOWN"

        file_path = os.path.join(root, filename)
        doc = fitz.open(file_path)

        # Persistent Document-Level Tracking State
        active_statement = "UNKNOWN STATEMENT"
        current_subsection = ""

        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Native Text Extraction Step
            native_text = page.get_text("text")
            words = page.get_text("words")

            # Page-Level Conditional Fallback
            if not native_text or not native_text.strip() or not words:
                temp_img_path = "temp_page.png"
                pix = page.get_pixmap(dpi=150)
                pix.save(temp_img_path)
                
                try:
                    ocr_text = pytesseract.image_to_string(temp_img_path, config="--psm 6")
                finally:
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
                
                if not ocr_text or not ocr_text.strip():
                    continue
                
                # Synthesize word positional tuples for downstream row-grouping logic
                words = []
                for line_idx, line in enumerate(ocr_text.splitlines()):
                    line_tokens = line.split()
                    if not line_tokens:
                        continue
                    y_val = line_idx * 15.0
                    for tok_idx, tok in enumerate(line_tokens):
                        x_val = tok_idx * 20.0
                        words.append((x_val, y_val, x_val + 15.0, y_val + 10.0, tok))
            else:
                # Digital-native orientation handling
                rect = page.rect
                is_landscape = rect.width > rect.height
                total_w = sum(w[2] - w[0] for w in words)
                total_h = sum(w[3] - w[1] for w in words)
                is_sideways = total_h > total_w

                if is_landscape or is_sideways:
                    page.set_rotation((page.rotation + 90) % 360)
                    rect = page.rect
                    words = page.get_text("words")
                    if not words:
                        continue
                    total_w = sum(w[2] - w[0] for w in words)
                    total_h = sum(w[3] - w[1] for w in words)
                    if total_h > total_w or rect.width > rect.height:
                        page.set_rotation((page.rotation + 90) % 360)
                        rect = page.rect
                        words = page.get_text("words")

            if not words:
                continue

            rect = page.rect
            page_height = rect.height if rect.height > 0 else 1000.0
            
            rows_by_y = {}
            for w in words:
                x0, y0, x1, y1, word_str = w[:5]
                if y1 > page_height * 0.96:
                    continue
                matched_y = None
                for stored_y in rows_by_y.keys():
                    if abs(stored_y - y0) < 4:
                        matched_y = stored_y
                        break
                if matched_y is not None:
                    rows_by_y[matched_y].append((x0, y0, x1, y1, word_str))
                else:
                    rows_by_y[y0] = [(x0, y0, x1, y1, word_str)]

            sorted_y_keys = sorted(rows_by_y.keys())

            total_data_rows_count = 0
            for y_key in sorted_y_keys:
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                row_tokens = [w[4].strip() for w in row_words if w[4].strip()]
                num_count = sum(1 for token in row_tokens if financial_num_pattern.match(token.replace(" ", "")))
                if num_count >= 1:
                    total_data_rows_count += 1

            if total_data_rows_count < 2:
                continue

            # Check top 45% of page for new explicit statement headers
            for y_key in sorted_y_keys:
                if y_key > page_height * 0.45:
                    break
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                line_text = " ".join([w[4].strip() for w in row_words if w[4].strip()])
                if not line_text:
                    continue
                stmt_match = statement_pattern.match(line_text)
                if stmt_match:
                    active_statement = stmt_match.group(0).strip().upper()[:250]
                    current_subsection = ""  # Reset subsection on explicit statement title change
                    break

            detected_years = []
            for y_key in sorted_y_keys[:8]:
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                row_str = " ".join([w[4] for w in row_words])
                for yr in year_extractor.findall(row_str):
                    clean_yr = clean_year_string(yr)
                    if clean_yr not in detected_years:
                        detected_years.append(clean_yr)

            if not detected_years:
                detected_years = [file_pdf_year, file_pdf_year - 1]

            records_to_insert = []

            for y_key in sorted_y_keys:
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                tokens = [w[4].strip() for w in row_words if w[4].strip()]
                if not tokens:
                    continue

                full_row_str = " ".join(tokens)

                # Sticky Subsections & Statement Header Transitions (Non-numeric lines)
                if not any(char.isdigit() for char in full_row_str):
                    in_body_stmt = statement_pattern.match(full_row_str)
                    if in_body_stmt:
                        active_statement = in_body_stmt.group(0).strip().upper()[:250]
                        current_subsection = ""
                    else:
                        sub_str = full_row_str.upper()
                        if re.search(r'(NOTE|RUPEES|AMOUNTS?|---|RESTATED|AUDITED|\d{4})', sub_str) or len(tokens) > 6:
                            pass
                        else:
                            current_subsection = sub_str[:250]
                    continue

                # End-Anchored Text Splitting (Right-to-Left)
                numeric_values = []
                split_idx = len(tokens)

                for i in range(len(tokens) - 1, -1, -1):
                    token = tokens[i]
                    clean_tok = token.replace(" ", "")
                    if financial_num_pattern.match(clean_tok) or (re.search(r'\d', clean_tok) and not re.search(r'[A-Za-z]{3,}', clean_tok)):
                        numeric_values.insert(0, token)
                        split_idx = i
                    else:
                        break

                label_tokens = tokens[:split_idx]
                raw_line_item_label = " ".join(label_tokens).strip()

                # Clean trailing/leading dots, dashes, and whitespace
                raw_line_item_label = re.sub(r'[\.\s\-_]+$', '', raw_line_item_label)
                raw_line_item_label = re.sub(r'^[\.\s\-_]+', '', raw_line_item_label)

                line_item_label = clean_item_label(raw_line_item_label)

                if not line_item_label or not re.search(r'[A-Za-z]', line_item_label):
                    continue

                for idx, val in enumerate(numeric_values):
                    if not val or not re.search(r'\d', val):
                        continue

                    data_year = detected_years[idx] if idx < len(detected_years) else file_pdf_year

                    records_to_insert.append((
                        "FMCG",
                        clean_org[:250],
                        file_pdf_year,
                        active_statement,
                        current_subsection,
                        line_item_label,
                        clean_year_string(data_year),
                        val[:250]
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
                    (pyodbc.SQL_VARCHAR, 255)
                ])
                cursor.fast_executemany = True
                cursor.executemany(insert_sql, records_to_insert)
                conn.commit()

        doc.close()

cursor.close()
conn.close()