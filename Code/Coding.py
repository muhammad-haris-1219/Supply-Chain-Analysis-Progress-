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

for page_num in range(len(doc)):
    page = doc[page_num]
    page_mid_x = page.rect.width / 2

    global_page_title = "STATEMENT_CONTINUED"
    page_dict = page.get_text("dict")

    found_global_title = False
    for block in page_dict["blocks"]:
        if "lines" in block:
            for line in block["lines"]:
                line_text = " ".join([span["text"] for span in line["spans"]]).strip()
                if universal_statement_pattern.search(line_text) and len(line_text) < 80:
                    if "NOTE" not in line_text.upper() and "INTEGRAL" not in line_text.upper():
                        global_page_title = line_text
                        found_global_title = True
                        break
            if found_global_title:
                break

    all_words = page.get_text("words")

    left_data_bounds = []
    right_data_bounds = []
    for w in all_words:
        w_x0, w_y0, w_x1, w_y1, text, _, _, _ = w
        clean_txt = text.replace(",", "").replace("(", "").replace(")", "").strip()
        if (clean_txt.isdigit() or text == "-") and len(clean_txt) > 0:
            if w_x0 < page.rect.width * 0.45:
                left_data_bounds.append(w_x1)
            elif w_x0 > page.rect.width * 0.52:
                right_data_bounds.append(w_x0)

    adaptive_dividing_x = page.rect.width / 2
    if left_data_bounds and right_data_bounds:
        max_left_projection = max(left_data_bounds)
        min_right_projection = min(right_data_bounds)
        if min_right_projection > max_left_projection:
            adaptive_dividing_x = (max_left_projection + min_right_projection) / 2.0

    layout_zones = [
        {"name": "LEFT", "rect": fitz.Rect(0, 0, adaptive_dividing_x - 5, page.rect.height), "y_tol": 3.5, "split_ratio": 0.35},
        {"name": "RIGHT", "rect": fitz.Rect(adaptive_dividing_x + 5, 0, page.rect.width, page.rect.height), "y_tol": 1.2, "split_ratio": 0.15}
    ]

    for zone in layout_zones:
        zone_rect = zone["rect"]
        zone_words = [w for w in all_words if fitz.Rect(w[:4]).intersects(zone_rect)]

        zone_statement_title = ""
        zone_lines_temp = {}
        for w in zone_words:
            w_x0, w_y0, w_x1, w_y1, text, _, _, _ = w
            y_k = round(w_y0 / 2.0) * 2.0
            if y_k not in zone_lines_temp:
                zone_lines_temp[y_k] = []
            zone_lines_temp[y_k].append((w_x0, text))

        for y_k in sorted(zone_lines_temp.keys()):
            line_str = " ".join([w[1] for w in sorted(zone_lines_temp[y_k], key=lambda x: x[0])]).strip()
            if universal_statement_pattern.search(line_str) and len(line_str) < 80:
                if "NOTE" not in line_str.upper() and "INTEGRAL" not in line_str.upper():
                    zone_statement_title = line_str
                    break

        if not zone_statement_title:
            zone_statement_title = global_page_title

        page_lines = {}
        for w in zone_words:
            w_x0, w_y0, w_x1, w_y1, text, block_no, line_no, word_no = w
            y_key = round(w_y0 / zone["y_tol"]) * zone["y_tol"]
            if y_key not in page_lines:
                page_lines[y_key] = []
            page_lines[y_key].append((w_x0, w_x1, w_y0, text))

        sorted_y_lines = sorted(page_lines.keys())

        if not sorted_y_lines:
            continue

        gaps = [sorted_y_lines[i+1] - sorted_y_lines[i] for i in range(len(sorted_y_lines)-1)]
        filtered_gaps = [g for g in gaps if 4.0 < g < 25.0]
        avg_page_gap = sum(filtered_gaps) / len(filtered_gaps) if filtered_gaps else 12.0
        adaptive_threshold = avg_page_gap * 0.70

        raw_centers = []
        center_frequencies = {}
        first_data_row_y = None
        first_numeric_x0 = None
        approx_start_x = zone_rect.x0 + (zone_rect.x1 - zone_rect.x0) * zone["split_ratio"]

        for y in sorted_y_lines:
            line_words = sorted(page_lines[y], key=lambda x: x[0])
            num_tokens = []
            for w_x0, w_x1, w_y0, text in line_words:
                clean_txt = text.replace(",", "").replace("(", "").replace(")", "").strip()
                if (clean_txt.isdigit() or text == "-") and len(clean_txt) > 0:
                    if w_x0 > approx_start_x:
                        num_tokens.append((w_x0, w_x1))

            if len(num_tokens) >= 2:
                if first_data_row_y is None:
                    first_data_row_y = y
                    first_numeric_x0 = num_tokens[0][0]
                for w_x0, w_x1 in num_tokens:
                    center_x = (w_x0 + w_x1) / 2

                    matched_existing = False
                    for c in raw_centers:
                        if abs(center_x - c) < 20:
                            center_frequencies[c] += 1
                            matched_existing = True
                            break
                    if not matched_existing:
                        raw_centers.append(center_x)
                        center_frequencies[center_x] = 1

        if zone["name"] == "LEFT":
            detected_column_centers = [c for c in raw_centers if center_frequencies[c] >= 4]
        else:
            detected_column_centers = [c for c in raw_centers if center_frequencies[c] >= 4 or (first_data_row_y and center_frequencies[c] >= 1)]
            
        detected_column_centers.sort()
        total_cols = len(detected_column_centers)

        if total_cols == 0:
            continue

        print("\n====================================================================================")
        print(f"🚀 SLICING GRIDS ENGINE: EXECUTING {zone['name']} CLIPPED ZONE ON PAGE {page_num}")
        print(f"Dynamic Title Header: '{zone_statement_title}'")
        print("====================================================================================")

        DATA_LABEL_END_X = (
            first_numeric_x0 - 25
            if first_numeric_x0
            else detected_column_centers[0] - 25
        )
        HEADER_LABEL_END_X = zone_rect.x0

        header_pockets = {i: {} for i in range(total_cols)}

        for y in sorted_y_lines:
            if first_data_row_y and y >= first_data_row_y:
                continue

            line_words = sorted(page_lines[y], key=lambda x: x[0])
            full_line_str = " ".join([w[3] for w in line_words])

            if "---" in full_line_str or "___" in full_line_str:
                continue
            if any(w[0] < HEADER_LABEL_END_X for w in line_words):
                continue

            for w_x0, w_x1, w_y0, text in line_words:
                if w_x0 >= HEADER_LABEL_END_X:
                    clean_text = text.strip()
                    if clean_text == "-":
                        continue

                    mid_x = (w_x0 + w_x1) / 2
                    for idx, center_x in enumerate(detected_column_centers):
                        col_min_x = HEADER_LABEL_END_X if idx == 0 else (detected_column_centers[idx - 1] + center_x) / 2
                        col_max_x = zone_rect.x1 if idx == total_cols - 1 else (center_x + detected_column_centers[idx + 1]) / 2

                        if col_min_x - 5 <= mid_x <= col_max_x + 5:
                            y_line_key = round(w_y0 / 2) * 2
                            if y_line_key not in header_pockets[idx]:
                                header_pockets[idx][y_line_key] = []
                            header_pockets[idx][y_line_key].append((w_x0, clean_text))
                            break

        dynamic_headers = ["Statement Type", "Row Label"]
        for idx in range(total_cols):
            pocket_lines = header_pockets[idx]
            sorted_y_keys = sorted(pocket_lines.keys())
            line_strings = []
            for y_key in sorted_y_keys:
                sorted_line_words = sorted(pocket_lines[y_key], key=lambda x: x[0])
                line_str = " ".join([w[1] for w in sorted_line_words]).strip()
                if line_str:
                    line_strings.append(line_str)

            constructed_title = " ".join(line_strings).strip()
            constructed_title = constructed_title.replace("- ", "")
            if not constructed_title:
                constructed_title = f"Column_{idx+1}"
            dynamic_headers.append(constructed_title)

        print("COLUMNS MAPPED:", " | ".join(dynamic_headers))
        print("-" * 145)

        buffered_label = ""
        prev_real_y = None
        prev_line_x0 = None

        for y in sorted_y_lines:
            if first_data_row_y and y < first_data_row_y:
                continue

            words_in_line = page_lines[y]
            line_words_sorted = sorted(words_in_line, key=lambda x: x[0])

            label_pieces = []
            value_slots = ["-"] * total_cols
            has_numeric_data = False
            current_line_y_pos = y
            current_line_x0_pos = None

            for w_x0, w_x1, w_y0, text in line_words_sorted:
                current_line_y_pos = w_y0
                if current_line_x0_pos is None:
                    current_line_x0_pos = w_x0
                if w_x0 < DATA_LABEL_END_X:
                    label_pieces.append(text)
                else:
                    clean_txt = (
                        text.replace(",", "")
                        .replace("(", "")
                        .replace(")", "")
                        .strip()
                    )
                    if clean_txt.isdigit() or text == "-":
                        mid_x = (w_x0 + w_x1) / 2
                        for idx, center_x in enumerate(detected_column_centers):
                            if abs(mid_x - center_x) < 32:
                                value_slots[idx] = text
                                has_numeric_data = True
                                break

            current_label_str = " ".join(label_pieces).strip()

            if (
                not current_label_str
                or current_label_str.startswith("---")
                or current_label_str.startswith("___")
                or len(current_label_str) <= 2
            ):
                continue
                
            is_tight_line = False
            if prev_real_y is not None and (current_line_y_pos - prev_real_y) < adaptive_threshold:
                is_tight_line = True
            if prev_line_x0 is not None and current_line_x0_pos is not None:
                if current_line_x0_pos > prev_line_x0 + 4.0:
                    is_tight_line = True
                    
            prev_real_y = current_line_y_pos
            prev_line_x0 = current_line_x0_pos
            
            if not has_numeric_data:
                if buffered_label and not is_tight_line:
                    print(f"➔ {[zone_statement_title, buffered_label] + ['-'] * total_cols}")
                    buffered_label = current_label_str
                else:
                    buffered_label = (
                        f"{buffered_label} {current_label_str}".strip()
                        if buffered_label
                        else current_label_str
                    )
            else:
                if buffered_label and not is_tight_line:
                    print(f"➔ {[zone_statement_title, buffered_label] + ['-'] * total_cols}")
                    final_row_label = current_label_str
                else:
                    final_row_label = (
                        f"{buffered_label} {current_label_str}".strip()
                        if buffered_label
                        else current_label_str
                    )
                final_output_row = [zone_statement_title, final_row_label] + value_slots
                print(f"➔ {final_output_row}")
                buffered_label = ""
                
        if buffered_label and len(buffered_label) > 4:
            print(f"➔ {[zone_statement_title, buffered_label] + ['-'] * total_cols}")
            
        print("====================================================================================")

doc.close()