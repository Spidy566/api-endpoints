import re
import time
import uuid
from typing import Dict, Any
from fastapi import HTTPException
from core.config import BUCKET, logger
from core.dependencies import s3_client, textract_client

# --- 1. Cargo Manifest Extractor Class ---
class CargoManifestExtractor:
    """
    Extracts key-value pairs, tables, and text from documents using AWS Textract.
    """
    def __init__(self):
        self.client = textract_client

    def extract_manifest_data(self, document_bytes: bytes, content_type: str) -> Dict[str, Any]:
        min_conf = 85.0
        weight_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(KG|KGS|KG\(S\))', re.IGNORECASE)

        if content_type == 'application/pdf':
            key = f"{uuid.uuid4()}.pdf"
            s3_client.put_object(Bucket=BUCKET, Key=key, Body=document_bytes)

            job = self.client.start_document_analysis(
                DocumentLocation={'S3Object': {'Bucket': BUCKET, 'Name': key}},
                FeatureTypes=['TABLES', 'FORMS']
            )
            job_id = job['JobId']

            while True:
                res = self.client.get_document_analysis(JobId=job_id)
                status = res.get('JobStatus')
                if status == 'SUCCEEDED':
                    response = res
                    break
                if status == 'FAILED':
                    raise Exception('Textract job failed')
                time.sleep(1)
        else:
            response = self.client.analyze_document(Document={'Bytes': document_bytes}, FeatureTypes=['TABLES', 'FORMS'])

        blocks = response.get('Blocks', [])
        block_map = {b['Id']: b for b in blocks}

        def get_text(b: Dict[str, Any]) -> str:
            text = ''
            for rel in b.get('Relationships', []):
                if rel['Type'] == 'CHILD':
                    for cid in rel['Ids']:
                        c = block_map.get(cid)
                        if c and c['BlockType'] == 'WORD':
                            text += c.get('Text', '') + ' '
                        elif c and c['BlockType'] == 'SELECTION_ELEMENT' and c.get('SelectionStatus') == 'SELECTED':
                            text += 'X '
            return text.strip()

        key_map, value_map = {}, {}
        for b in blocks:
            if b['BlockType'] == 'KEY_VALUE_SET':
                types = b.get('EntityTypes', [])
                if 'KEY' in types:
                    key_map[b['Id']] = b
                elif 'VALUE' in types:
                    value_map[b['Id']] = b

        kv_dict = {}
        for key_id, key_block in key_map.items():
            if key_block.get('Confidence', 0.0) < min_conf:
                continue
            val_block = None
            for rel in key_block.get('Relationships', []):
                if rel['Type'] == 'VALUE':
                    val_block = value_map.get(rel['Ids'][0])
                    break
            if val_block and val_block.get('Confidence', 0.0) < min_conf:
                continue
            raw_key = get_text(key_block)
            raw_val = get_text(val_block) if val_block else ''

            if 'agent' in raw_key.lower() and raw_val:
                raw_val = ' '.join(w.capitalize() for w in raw_val.split())
            if weight_pattern.search(raw_val):
                num = float(weight_pattern.search(raw_val).group(1))
                raw_val = f"{num:.2f} KG"
            kv_dict[raw_key] = raw_val

        tables = []
        for b in blocks:
            if b['BlockType'] == 'TABLE':
                cells = [block_map[cid] for rel in b.get('Relationships', []) if rel['Type'] == 'CHILD' for cid in rel['Ids']]
                rows = {}
                for cell in cells:
                    if cell['BlockType'] != 'CELL': continue
                    r, cidx = cell.get('RowIndex', 0), cell.get('ColumnIndex', 0)
                    rows.setdefault(r, {})[cidx] = get_text(cell)
                table_data = [[rows[r][c] for c in sorted(rows[r].keys())] for r in sorted(rows.keys())]
                tables.append(table_data)

        parsed_tables = []
        for table_data in tables:
            if not table_data: continue
            if len(table_data[0]) == 2:
                parsed_tables.append({row[0]: row[1] for row in table_data})
            else:
                headers = table_data[0]
                parsed_tables.append([
                    {headers[i]: row[i] for i in range(len(headers))} for row in table_data[1:]
                ])

        return {'key_value_pairs': kv_dict, 'tables': parsed_tables}

# --- 2. Expense Analysis Logic ---
def parse_expense_response(job_id: str) -> Dict:
    try:
        pages = []
        response = textract_client.get_expense_analysis(JobId=job_id)
        pages.append(response)
        token = response.get("NextToken", None)
        while token:
            response = textract_client.get_expense_analysis(JobId=job_id, NextToken=token)
            pages.append(response)
            token = response.get("NextToken", None)
    except Exception as e:
        logger.error(f"ExpenseAnalysis retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Textract retrieval failed: {str(e)}")

    extracted_data = {
        "summary_fields": [],
        "line_items": []
    }

    for page in pages:
        for doc in page.get("ExpenseDocuments", []):
            for field in doc.get("SummaryFields", []):
                label = field.get("LabelDetection", {}).get("Text", "").strip()
                value = field.get("ValueDetection", {}).get("Text", "").strip()
                if label or value:
                    extracted_data["summary_fields"].append({
                        "label": label,
                        "value": value
                    })

            for group in doc.get("LineItemGroups", []):
                for item in group.get("LineItems", []):
                    row = {}
                    for field in item.get("LineItemExpenseFields", []):
                        label = field.get("LabelDetection", {}).get("Text", "").strip()
                        value = field.get("ValueDetection", {}).get("Text", "").strip()
                        if label or value:
                            row[label] = value
                    if row:
                        extracted_data["line_items"].append(row)
    return extracted_data

# --- 3. Document/Invoice Analysis Logic ---
def parse_vendor_invoice_response(job_id: str) -> Dict:
    try:
        pages = []
        response = textract_client.get_document_analysis(JobId=job_id)
        pages.append(response)
        token = response.get("NextToken", None)
        while token:
            response = textract_client.get_document_analysis(JobId=job_id, NextToken=token)
            pages.append(response)
            token = response.get("NextToken", None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Textract retrieval failed: {str(e)}")

    block_map = {}
    key_map = {}
    value_map = {}
    table_blocks = []

    for page in pages:
        for block in page["Blocks"]:
            block_map[block["Id"]] = block
            if block["BlockType"] == "KEY_VALUE_SET":
                if "KEY" in block["EntityTypes"]:
                    key_map[block["Id"]] = block
                else:
                    value_map[block["Id"]] = block
            elif block["BlockType"] == "TABLE":
                table_blocks.append(block)

    def get_text(block):
        text = ""
        if "Relationships" in block:
            for rel in block["Relationships"]:
                if rel["Type"] == "CHILD":
                    for cid in rel["Ids"]:
                        word = block_map.get(cid, {})
                        if word.get("BlockType") == "WORD":
                            text += word.get("Text", "") + " "
                        elif word.get("BlockType") == "SELECTION_ELEMENT" and word.get("SelectionStatus") == "SELECTED":
                            text += "X "
        return text.strip()

    # Extract header fields
    header_fields = {}
    for key_id, key_block in key_map.items():
        key_text = get_text(key_block)
        val_text = ""
        if "Relationships" in key_block:
            for rel in key_block["Relationships"]:
                if rel["Type"] == "VALUE":
                    for val_id in rel["Ids"]:
                        val_block = value_map.get(val_id)
                        val_text = get_text(val_block)
        if key_text:
            header_fields[key_text] = val_text

    def extract_table(table_block):
        rows = {}
        for block in pages[0]["Blocks"]:
            if block["BlockType"] == "CELL" and block.get("Page") == table_block.get("Page"):
                row = block["RowIndex"]
                col = block["ColumnIndex"]
                text = get_text(block)
                rows.setdefault(row, {})[col] = text

        headers = rows.get(1, {})
        table_data = []
        for row_idx in sorted(rows.keys()):
            if row_idx == 1:
                continue
            row_data = {}
            for col_idx, col_val in rows[row_idx].items():
                col_name = headers.get(col_idx, f"Column{col_idx}")
                row_data[col_name] = col_val
            table_data.append(row_data)
        return table_data

    charges_table = []
    container_table = []
    for table in table_blocks:
        table_data = extract_table(table)
        table_str = " ".join([",".join(row.values()) for row in table_data]).lower()
        if "container" in table_str:
            container_table.extend(table_data)
        else:
            charges_table.extend(table_data)

    # Remove duplicates
    seen = set()
    deduped_charges = []
    for row in charges_table:
        key = tuple((k.lower().strip(), v.lower().strip()) for k, v in row.items())
        if key not in seen:
            deduped_charges.append(row)
            seen.add(key)

    return {
        "header_fields": header_fields,
        "charges_table": deduped_charges,
        "container_table": container_table
    }