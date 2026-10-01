import re
import pymupdf as fitz

pdf_path = r"D:\WMA\Python\Project\Files\Engro\Engro 2021.pdf"
doc = fitz.open(pdf_path)

universal_statement_pattern = re.compile(
    r"(?:"
    r"(?:CONDENSED\s+)?"
    r"(?:CONSOLIDATED\s+|UNCONSOLIDATED\s+|GROUP\s+)?"
    r"(?:"
    r"STATEMENT\s+OF\s+FINANCIAL\s+POSITION|"
    r"STATEMENT\s+OF\s+PROFIT\s+OR\s+LOSS(?:\s+AND\s+OTHER\s+COMPREHENSIVE\s+INCOME)?|"
    r"STATEMENT\s+OF\s+CHANGES\s+IN\s+EQUITY|"
    r"STATEMENT\s+OF\s+CASH\s+FLOWS?|"
    r"STATEMENT\s+OF\s+COMPREHENSIVE\s+INCOME|"
    r"STATEMENT\s+OF\s+VALUE\s+ADDITION\s+(?:AND|&)\s+DISTRIBUTION|"
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
    r"FINANCIAL\s+PERFORMANCE\s+INDICATORS|"
    r"SUMMARY\s+OF\s+PROFIT\s+OR\s+LOSS|"
    r"FINANCIAL\s+STATEMENTS?"
    r")"
    r")",
    re.IGNORECASE,
)

SECTION_HEADER_PATTERN = re.compile(
    r"^(?:CASH\s+FLOWS\s+FROM|PURCHASES\s+OF|PROCEEDS\s+FROM|RESERVES|CAPITAL\s+RESERVES|REVENUE\s+RESERVE)",
    re.IGNORECASE
)

global_title_tracker = None

for page_num in range(len(doc)):
    page = doc[page_num]
    all_words = page.get_text("words")

    if not all_words:
        continue

    word_heights = [w[3] - w[1] for w in all_words if (w[3] - w[1]) > 0]
    median_height = sorted(word_heights)[len(word_heights) // 2] if word_heights else 10.0
    dynamic_y_tol = max(1.0, median_height * 0.35)

    left_data_bounds = []
    right_data_bounds = []
    for w in all_words:
        w_x0, w_y0, w_x1, w_y1, text, _, _, _ = w
        clean_txt = text.replace(",", "").replace("(", "").replace(")", "").strip()
        if (clean_txt.isdigit() or text == "-") and len(clean_txt) > 0:
            if w_x0 < page.rect.width * 0.48:
                left_data_bounds.append(w_x1)
            else:
                right_data_bounds.append(w_x0)

    adaptive_dividing_x = page.rect.width / 2.0
    if left_data_bounds and right_data_bounds:
        max_left = max(left_data_bounds)
        min_right = min(right_data_bounds)
        if min_right > max_left:
            adaptive_dividing_x = (max_left + min_right) / 2.0

    layout_zones = [
        {"name": "LEFT", "rect": fitz.Rect(0, 0, adaptive_dividing_x, page.rect.height)},
        {"name": "RIGHT", "rect": fitz.Rect(adaptive_dividing_x, 0, page.rect.width, page.rect.height)}
    ]

    for zone in layout_zones:
        zone_rect = zone["rect"]
        zone_words = [w for w in all_words if fitz.Rect(w[:4]).intersects(zone_rect)]

        if not zone_words:
            continue

        zone_lines_temp = {}
        for w in zone_words:
            w_x0, w_y0, w_x1, w_y1, text, _, _, _ = w
            y_k = round(w_y0 / dynamic_y_tol) * dynamic_y_tol
            zone_lines_temp.setdefault(y_k, []).append((w_x0, text))

        zone_statement_title = ""
        for y_k in sorted(zone_lines_temp.keys()):
            line_str = " ".join([w[1] for w in sorted(zone_lines_temp[y_k], key=lambda x: x[0])]).strip()
            if universal_statement_pattern.search(line_str) and len(line_str) < 80:
                if "NOTE" not in line_str.upper() and "INTEGRAL" not in line_str.upper():
                    zone_statement_title = line_str
                    global_title_tracker = line_str
                    break

        if not zone_statement_title:
            zone_statement_title = global_title_tracker if global_title_tracker else "FINANCIAL STATEMENT"

        page_lines = {}
        for w in zone_words:
            w_x0, w_y0, w_x1, w_y1, text, _, _, _ = w
            y_key = round(w_y0 / dynamic_y_tol) * dynamic_y_tol
            page_lines.setdefault(y_key, []).append((w_x0, w_x1, w_y0, text))

        sorted_y_lines = sorted(page_lines.keys())
        if not sorted_y_lines:
            continue

        raw_centers = []
        center_frequencies = {}
        first_data_row_y = None
        first_numeric_word_x0 = None

        for y in sorted_y_lines:
            line_words = sorted(page_lines[y], key=lambda x: x[0])
            line_full_str = " ".join([w[3] for w in line_words]).upper()

            if any(k in line_full_str for k in ["FOR THE YEAR", "ANNUAL REPORT", "FRIESLANDCAMPINA"]):
                continue

            num_tokens = []
            for w_x0, w_x1, w_y0, text in line_words:
                clean_txt = text.replace(",", "").replace("(", "").replace(")", "").strip()
                if (clean_txt.isdigit() or text == "-") and len(clean_txt) > 0:
                    if clean_txt in ["1", "31", "2020", "2021"] and w_x0 < (zone_rect.x0 + zone_rect.width * 0.30):
                        continue
                    num_tokens.append((w_x0, w_x1))

            if len(num_tokens) >= 1:
                if first_data_row_y is None and len(num_tokens) >= 2:
                    first_data_row_y = y
                
                if first_numeric_word_x0 is None and len(num_tokens) >= 2:
                    first_numeric_word_x0 = num_tokens[0][0]

                for w_x0, w_x1 in num_tokens:
                    center_x = (w_x0 + w_x1) / 2.0
                    matched_existing = False
                    for c in raw_centers:
                        if abs(center_x - c) < (median_height * 2.5):
                            center_frequencies[c] += 1
                            matched_existing = True
                            break
                    if not matched_existing:
                        raw_centers.append(center_x)
                        center_frequencies[center_x] = 1

        detected_column_centers = sorted([c for c in raw_centers if center_frequencies[c] >= 2])
        total_cols = len(detected_column_centers)

        if total_cols == 0:
            continue

        if first_numeric_word_x0:
            DATA_LABEL_END_X = first_numeric_word_x0 - (median_height * 0.5)
        else:
            DATA_LABEL_END_X = detected_column_centers[0] - (median_height * 1.0)

        print("\n====================================================================================")
        print(f"🚀 SLICING GRIDS ENGINE: EXECUTING {zone['name']} CLIPPED ZONE ON PAGE {page_num}")
        print(f"Dynamic Title Header: '{zone_statement_title}'")
        print("====================================================================================")

        header_pockets = {i: [] for i in range(total_cols)}

        title_y_start = None
        for y in sorted_y_lines:
            line_str = " ".join([w[3] for w in sorted(page_lines[y], key=lambda x: x[0])]).strip()
            if zone_statement_title in line_str:
                title_y_start = y
                break

        if title_y_start is None:
            title_y_start = sorted_y_lines[0]

        for y in sorted_y_lines:
            if first_data_row_y and title_y_start <= y < first_data_row_y:
                line_words = sorted(page_lines[y], key=lambda x: x[0])
                line_text_upper = " ".join([w[3] for w in line_words]).upper()

                if any(k in line_text_upper for k in ["FOR THE YEAR", "AMOUNTS IN", "CHAIRMAN", "OFFICER", "REPORT", "RUPEES", "---", zone_statement_title.upper()]):
                    continue

                for w_x0, w_x1, w_y0, text in line_words:
                    clean_txt = text.strip()
                    if not clean_txt or clean_txt == "-":
                        continue
                    if w_x0 >= DATA_LABEL_END_X:
                        mid_x = (w_x0 + w_x1) / 2.0
                        for idx, center_x in enumerate(detected_column_centers):
                            col_min_x = zone_rect.x0 if idx == 0 else (detected_column_centers[idx - 1] + center_x) / 2.0
                            col_max_x = zone_rect.x1 if idx == total_cols - 1 else (center_x + detected_column_centers[idx + 1]) / 2.0
                            if col_min_x <= mid_x <= col_max_x:
                                header_pockets[idx].append((w_y0, w_x0, clean_txt))
                                break

        constructed_headers = []
        for idx in range(total_cols):
            pocket_words = sorted(header_pockets[idx], key=lambda x: (x[0], x[1]))
            col_title = " ".join([w[2] for w in pocket_words]).strip()
            col_title = re.sub(r'^(RESERVES|CAPITAL|REVENUE|ACTIVITIES)\s+', '', col_title, flags=re.IGNORECASE)
            constructed_headers.append(col_title if col_title else f"Column_{idx+1}")

        print(f"➔ {[zone_statement_title, 'Description'] + constructed_headers}")

        buffered_label = ""

        for y in sorted_y_lines:
            if first_data_row_y and y < first_data_row_y:
                continue

            words_in_line = sorted(page_lines[y], key=lambda x: x[0])
            line_text_upper = " ".join([w[3] for w in words_in_line]).upper()

            if any(k in line_text_upper for k in ["CHAIRMAN", "OFFICER", "FRIESLANDCAMPINA", "ANNUAL REPORT"]):
                continue

            label_pieces = []
            value_slots = ["-"] * total_cols
            has_numeric_data = False

            for w_x0, w_x1, w_y0, text in words_in_line:
                if w_x0 < DATA_LABEL_END_X:
                    label_pieces.append(text)
                else:
                    clean_txt = text.replace(",", "").replace("(", "").replace(")", "").strip()
                    if clean_txt.isdigit() or text == "-":
                        mid_x = (w_x0 + w_x1) / 2.0
                        for idx, center_x in enumerate(detected_column_centers):
                            col_min_x = zone_rect.x0 if idx == 0 else (detected_column_centers[idx - 1] + center_x) / 2.0
                            col_max_x = zone_rect.x1 if idx == total_cols - 1 else (center_x + detected_column_centers[idx + 1]) / 2.0
                            if col_min_x <= mid_x <= col_max_x:
                                value_slots[idx] = text
                                has_numeric_data = True
                                break

            current_label_str = " ".join(label_pieces).strip()

            if not current_label_str or current_label_str.startswith("---") or current_label_str.startswith("___"):
                continue

            # Handling Section Headings (e.g. CASH FLOWS FROM OPERATING ACTIVITIES)
            if SECTION_HEADER_PATTERN.search(current_label_str) and not has_numeric_data:
                if buffered_label:
                    print(f"➔ {[zone_statement_title, buffered_label] + ['-'] * total_cols}")
                    buffered_label = ""
                print(f"➔ {[zone_statement_title, current_label_str] + ['-'] * total_cols}")
                continue

            if not has_numeric_data:
                buffered_label = f"{buffered_label} {current_label_str}".strip() if buffered_label else current_label_str
            else:
                final_row_label = f"{buffered_label} {current_label_str}".strip() if buffered_label else current_label_str
                print(f"➔ {[zone_statement_title, final_row_label] + value_slots}")
                buffered_label = ""

        if buffered_label and len(buffered_label) > 2:
            print(f"➔ {[zone_statement_title, buffered_label] + ['-'] * total_cols}")

        print("====================================================================================")

doc.close()