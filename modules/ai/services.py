import requests
import json
import base64
from core.config import logger
from modules.ai import utils


def process_with_openai(api_key: str, model: str, prompt_header: str, prompt_details: str,
                        base64_content: str, api_token: str, temperature: float,
                        top_p: float, timeout: int) -> dict:
    """Process document with OpenAI Vision API"""
    try:
        full_prompt = ""
        if prompt_header and prompt_details:
            full_prompt = f"{prompt_header}\n\n{prompt_details}"
        elif prompt_header:
            full_prompt = prompt_header
        elif prompt_details:
            full_prompt = prompt_details

        if not full_prompt.strip():
            return {"success": False, "error": "No prompt provided"}

        try:
            decoded_size = len(base64.b64decode(base64_content, validate=True))
            if decoded_size > 20 * 1024 * 1024:
                return {"success": False, "error": "File too large (>20MB)"}
        except Exception as e:
            return {"success": False, "error": f"Invalid base64: {str(e)}"}

        try:
            file_format = utils.detect_and_validate_format(base64_content)

            if file_format == "pdf":
                converted_images = utils.convert_pdf_to_jpeg(base64_content)
                file_format = "jpeg"
            else:
                converted_images = [base64_content]

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"File processing failed: {str(e)}"}

        content = [{"type": "text", "text": full_prompt}]

        for i, image_base64 in enumerate(converted_images):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{file_format};base64,{image_base64}",
                    "detail": "high"
                }
            })
            logger.info(f"Added image {i + 1}/{len(converted_images)} to request")

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": content
            }],
            "max_tokens": int(api_token),
            "temperature": temperature,
            "top_p": top_p
        }

        logger.info(f"Sending request to OpenAI with {len(converted_images)} images")
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=payload, timeout=timeout)

        if response.status_code == 200:
            result = response.json()

            if 'choices' not in result or len(result['choices']) == 0:
                return {"success": False, "error": "Invalid API response structure"}

            ai_response = result['choices'][0]['message']['content']
            logger.info(f"AI Response length: {len(ai_response) if ai_response else 0}")

            if not ai_response or not ai_response.strip():
                return {"success": False, "error": "AI returned empty response"}

            cleaned_response = ai_response.strip()

            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]

            cleaned_response = cleaned_response.strip()

            # Parse JSON response
            try:
                parsed_json = json.loads(cleaned_response)

                return {
                    "success": True,
                    "extracted_data": parsed_json
                }

            except json.JSONDecodeError as e:
                logger.error(f"JSON Parse Error: {str(e)}")
                logger.error(f"Raw AI Response: {ai_response[:500]}")
                return {
                    "success": False,
                    "error": f"JSON parsing failed: {str(e)}",
                    "raw_response": ai_response[:500]
                }

        # Handle API errors
        error_map = {
            429: "Rate limit exceeded",
            400: "Bad request - check parameters",
            401: "Invalid API key",
            403: "Insufficient permissions",
            500: "OpenAI server error"
        }

        return {"success": False, "error": error_map.get(response.status_code, f"API error: {response.status_code}")}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timeout"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection error"}
    except Exception as e:
        return {"success": False, "error": f"Processing error: {str(e)}"}

def extract_card_json_with_openai(api_key: str, model: str, raw_text: str, cleaned_text: str, timeout: int = 120) -> dict:
    """Extract structured JSON from OCR text using OpenAI"""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    system_msg = {
        "role": "system",
        "content": (
            "You are an AI data extractor. "
            "Your only task is to output valid JSON. "
            "Do not include explanations, text, or markdown. "
            "Output must be a single JSON object following exactly the required keys."
        ),
    }

    user_prompt = f"""
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

    payload = {
        "model": model,
        "messages": [system_msg, {"role": "user", "content": user_prompt}],
    }

    if model.startswith("gpt-5"):
        payload["max_completion_tokens"] = 800
    else:
        payload["max_tokens"] = 800
        payload["temperature"] = 0.1
        payload["top_p"] = 0.9

    def call_openai() -> dict:
        resp = requests.post("https://api.openai.com/v1/chat/completions",
                             headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return {"error": f"OpenAI API error {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": content.strip()}

    result = call_openai()
    text = result.get("text", "").strip()

    if not text:
        result = call_openai()
        text = result.get("text", "").strip()

    if not text:
        return {"error": "Empty response from model", "raw": ""}

    for fence in ["```json", "```"]:
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception as e:
        return {"error": f"Failed to parse JSON: {e}", "raw": text[:1000]}