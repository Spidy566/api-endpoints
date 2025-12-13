VC_SCAN_SYSTEM_MESSAGE = {
        "role": "system",
        "content": (
            "You are an AI data extractor. "
            "Your only task is to output valid JSON. "
            "Do not include explanations, text, or markdown. "
            "Output must be a single JSON object following exactly the required keys."
        ),
    }

VC_SCAN_USER_TEMPLATE = """
Extract structured contact information from the OCR text below.

Rules:
1️⃣ Always detect multiple companies, phone numbers, and addresses if they exist.
2️⃣ Each key must contain an array of strings, even if one value.
3️⃣ Required keys:
   - name
   - designation
   - company_name
   - emails
   - phone_numbers
   - address
   - city
   - country
   - website
   - slogan
4️⃣ Merge multi-line addresses but keep different locations separate.
5️⃣ Fix OCR mistakes (e.g. '@ ' → '@', 'dot' → '.').

Example:
{{
  "name": ["John Smith"],
  "designation": ["Sales Director"],
  "company_name": ["ABC Logistics", "XYZ Shipping"],
  "emails": ["john@abclogistics.com"],
  "phone_numbers": ["+1 212-555-7890", "+971 50 123 4567"],
  "address": ["123 Main St, New York, USA", "Dubai Marina, UAE"],
  "city": ["New York", "Dubai"],
  "country": ["USA", "UAE"],
  "website": ["www.abclogistics.com"],
  "slogan": ["We move the world"]
}}

Now extract from:

Raw OCR:
\"\"\"{raw_text}\"\"\"

Cleaned OCR:
\"\"\"{cleaned_text}\"\"\"
"""

BL_EXTRACTION_SYSTEM = "You are a data extraction engine. You strictly output JSON based on the provided schema."

BL_EXTRACTION_USER = """
You are a logistics document expert. Extract data from this Bill of Lading (BL) into the specific JSON format defined below.

INSTRUCTIONS FOR HANDLING DIFFERENT LAYOUTS:
1. **Labels:** Look for synonyms. 
   - "Consignor" = "Shipper" = "From"
   - "MBL/MTD no" = "B/L No" = "Bill of Lading No" = "Document No"
   - "Notify Party" = "Notify" = "Notify Address"
2. **Structure:** If fields (like Goods Description) span multiple lines or pages, combine them into a single string.
3. **Addresses:** Join address lines with a "\\n" character.
4. **Data Types:** Keep all values as strings. Maintain commas in numbers (e.g., "2,500.00").
5. **Containers:** Extract all containers listed in the container/marks table section into the `container` array.

REQUIRED JSON OUTPUT STRUCTURE:
Return ONLY valid JSON. Do not include markdown formatting.

{
  "mbl_mtd_no": "The main BL number",
  "consignor_shipper": "Name\\nAddress Line 1\\nAddress Line 2...",
  "consignee": "Name\\nAddress Line 1\\nAddress Line 2...",
  "notify_party": "Name\\nAddress Line 1\\nAddress Line 2...",
  "place_of_receipt": "City/Location where goods were received",
  "port_of_loading": "Port Name",
  "freight_payable_at": "Location",
  "vessel": "Vessel Name and Voyage Number",
  "port_of_discharge": "Port Name",
  "place_of_delivery": "Final Delivery Location",
  "number_of_original_bill_of_lading": "Count (e.g., 'THREE (3)')",
  "mark_and_numbers": "Full text from the Marks & Numbers column",
  "number_of_packages": "Total count (e.g., '721 CARTONS')",
  "stc_kind_of_packages_description_of_goods_instructions": "Full body text describing goods, HS codes, etc.",
  "gross_weight": "Total Gross Weight (e.g. '29,060.000')",
  "measurements": "Total Volume/Measurement (e.g. '66.515')",
  "shipped_onboard_date": "Date mentioned for Shipped on Board",
  "place_and_date_issue": "Place and Date mentioned for Issue",
  "delivery_agent": "Name and Address of Delivery/Release Agent",
  "container": [
    {
      "container_no": "Container Number (e.g., ABCD1234567)",
      "seal_no": "Seal Number",
      "no_of_pcs": "Package count inside this container",
      "gross_weight_kgs": "Weight for this specific container",
      "net_weight_kgs": "Net weight if available, else null"
    }
  ]
}
"""