import os
import re
import fitz
import pyodbc

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
    r"(?:CONSOLIDATED\s+|CONDENSED\s+|INTERIM\s+|UNAUDITED\s+|GROUP\s+|NOTES?\s+TO\s+THE\s+)*"
    r"(STATEMENT\s+OF\s+FINANCIAL\s+POSITION|"
    r"STATEMENT\s+OF\s+PROFIT\s+OR\s+LOSS(?:\s+AND\s+OTHER\s+COMPREHENSIVE\s+INCOME)?|"
    r"STATEMENT\s+OF\s+COMPREHENSIVE\s+INCOME|"
    r"STATEMENT\s+OF\s+CASH\s+FLOWS?|"
    r"STATEMENT\s+OF\s+CHANGES\s+IN\s+EQUITY|"
    r"BALANCE\s+SHEET|"
    r"INCOME\s+STATEMENT|"
    r"PROFIT\s+AND\s+LOSS\s+ACCOUNT|"
    r"OPERATING\s+AND\s+FINANCIAL\s+HIGHLIGHTS|"
    r"FINANCIAL\s+HIGHLIGHTS|"
    r"OPERATING\s+HIGHLIGHTS)",
    re.IGNORECASE
)

year_extractor = re.compile(r"\b(20\d{2})\b")
financial_num_pattern = re.compile(r"^[\(\$-]?\s*\d{1,3}(,\d{3})+(\.\d+)?\s*\)?$|^[\(\$-]?\s*\d{4,}(\.\d+)?\s*\)?$|^[\(\$-]?\s*\d{1,3}\s*\)?$")

for root, dirs, files in os.walk(base_folder):
    for filename in files:
        if not filename.lower().endswith(".pdf"):
            continue

        name_part, _ = os.path.splitext(filename)
        found_filename_years = [int(y) for y in year_extractor.findall(name_part)]
        file_pdf_year = max(found_filename_years) if found_filename_years else 2026

        clean_org = re.sub(r"\b(20\d{2})\b", "", name_part, flags=re.IGNORECASE)
        clean_org = re.sub(r'[-_]', ' ', clean_org)
        clean_org = re.sub(r'\s+', ' ', clean_org).strip().upper()
        if not clean_org:
            clean_org = "UNKNOWN"

        file_path = os.path.join(root, filename)
        doc = fitz.open(file_path)

        for page_num in range(len(doc)):
            page = doc[page_num]

            words = page.get_text("words")
            if not words:
                continue

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

            page_height = rect.height
            page_width = rect.width

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
            multi_num_rows_count = 0
            first_data_row_idx = None

            for idx, y_key in enumerate(sorted_y_keys):
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                row_tokens = [w[4].strip() for w in row_words if w[4].strip()]

                num_count = 0
                for token in row_tokens:
                    clean_tok = token.replace(" ", "")
                    if financial_num_pattern.match(clean_tok):
                        num_count += 1

                if num_count >= 1:
                    total_data_rows_count += 1
                    if first_data_row_idx is None:
                        first_data_row_idx = idx
                if num_count >= 2:
                    multi_num_rows_count += 1

            if total_data_rows_count < 2:
                continue

            active_statement = None

            for y_key in sorted_y_keys:
                if y_key > page_height * 0.45:
                    break

                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                line_text = " ".join([w[4].strip() for w in row_words if re.search(r'[A-Za-z]', w[4])])

                if not line_text:
                    continue

                stmt_match = statement_pattern.search(line_text)
                if stmt_match:
                    active_statement = stmt_match.group(0).strip().upper()[:250]
                    break

            if not active_statement:
                combined_top_text = ""
                for y_key in sorted_y_keys:
                    if y_key > page_height * 0.35:
                        break
                    row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                    combined_top_text += " " + " ".join([w[4].strip() for w in row_words])

                stmt_match_combined = statement_pattern.search(combined_top_text)
                if stmt_match_combined:
                    active_statement = stmt_match_combined.group(0).strip().upper()[:250]

            if not active_statement:
                for y_key in sorted_y_keys:
                    if y_key > page_height * 0.35:
                        break

                    row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                    line_text = " ".join([w[4].strip() for w in row_words if w[4].strip()])

                    if re.search(r'^\d+(\.\d+)*\s+[A-Za-z]', line_text) or (len(line_text.split()) < 10 and re.search(r'[A-Za-z]', line_text)):
                        if not re.match(r'^(annual report|page|\d+$)', line_text.strip(), re.IGNORECASE):
                            active_statement = line_text.strip().upper()[:250]
                            break

            if not active_statement:
                active_statement = "UNKNOWN STATEMENT"

            detected_years = []
            for y_key in sorted_y_keys[:8]:
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                row_str = " ".join([w[4] for w in row_words])
                years_in_row = year_extractor.findall(row_str)
                for yr in years_in_row:
                    int_yr = int(yr)
                    if int_yr not in detected_years:
                        detected_years.append(int_yr)

            if not detected_years:
                detected_years = [file_pdf_year, file_pdf_year - 1]

            current_subsection = "GENERAL"
            records_to_insert = []

            for y_key in sorted_y_keys:
                row_words = sorted(rows_by_y[y_key], key=lambda item: item[0])
                tokens = [w[4].strip() for w in row_words if w[4].strip()]
                if not tokens:
                    continue

                full_row_str = " ".join(tokens)

                if not any(char.isdigit() for char in full_row_str):
                    if len(tokens) < 10 and re.search(r'[A-Za-z]', full_row_str):
                        in_body_stmt = statement_pattern.search(full_row_str)
                        if in_body_stmt and active_statement == "UNKNOWN STATEMENT":
                            active_statement = in_body_stmt.group(0).strip().upper()[:250]
                            current_subsection = "GENERAL"
                        else:
                            current_subsection = full_row_str.upper()[:250]
                    continue

                label_tokens = []
                numeric_values = []
                found_first_numeric = False

                for token in tokens:
                    clean_tok = token.replace(" ", "")
                    is_num = bool(financial_num_pattern.match(clean_tok))

                    if not found_first_numeric:
                        if is_num:
                            found_first_numeric = True
                            numeric_values.append(token)
                        else:
                            label_tokens.append(token)
                    else:
                        if is_num or re.search(r'\d', clean_tok):
                            numeric_values.append(token)

                line_item_label = " ".join(label_tokens).strip()
                line_item_label = re.sub(r'^\d+[\.\)]\s*', '', line_item_label)

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
                        int(data_year),
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



