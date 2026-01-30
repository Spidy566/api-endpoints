import requests
import json
import base64
from typing import Dict, Any, List
from core.config import logger
from modules.ai import utils, prompts


def process_with_openai(api_key: str, model: str, prompt_header: str, prompt_details: str,
                        base64_content: str, api_token: str, temperature: float,
                        top_p: float, timeout: int) -> Dict[str, Any]:
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
        except Exception as b64_err:
            return {"success": False, "error": f"Invalid base64: {str(b64_err)}"}

        try:
            file_format = utils.detect_and_validate_format(base64_content)

            if file_format == "pdf":
                converted_images = utils.convert_pdf_to_jpeg(base64_content)
                file_format = "jpeg"
            else:
                converted_images = [base64_content]

        except ValueError as val_err:
            return {"success": False, "error": str(val_err)}
        except Exception as fmt_err:
            return {"success": False, "error": f"File processing failed: {str(fmt_err)}"}

        content: List[Dict[str, Any]] = [{"type": "text", "text": full_prompt}]

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
        payload: Dict[str, Any] = {
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

            try:
                parsed_json = json.loads(cleaned_response)

                return {
                    "success": True,
                    "extracted_data": parsed_json
                }

            except json.JSONDecodeError as json_err:
                logger.error(f"JSON Parse Error: {str(json_err)}")
                logger.error(f"Raw AI Response: {ai_response[:500]}")
                return {
                    "success": False,
                    "error": f"JSON parsing failed: {str(json_err)}",
                    "raw_response": ai_response[:500]
                }

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
    except Exception as gen_err:
        return {"success": False, "error": f"Processing error: {str(gen_err)}"}


def scan_vc_with_vision(api_key: str, base64_file: str, model: str) -> Dict[str, Any]:
    """Extracts both raw text and parsed data from a VC using OpenAI Vision."""
    try:
        clean_b64 = utils.extract_base64_content(base64_file)
        if not clean_b64:
            return {"success": False, "error": "Invalid base64 provided"}

        try:
            base64_images = utils.extract_image(clean_b64)
        except Exception as conv_err:
            return {"success": False, "error": f"Image/PDF Conversion failed: {str(conv_err)}"}

        if not base64_images:
            return {"success": False, "error": "Could not extract images from input"}

        vision_content: List[Dict[str, Any]] = [
            {"type": "text", "text": prompts.VC_SCAN_USER_PROMPT}
        ]

        for img_b64 in base64_images:
            vision_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "high"}
            })

        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                prompts.VC_SCAN_SYSTEM_PROMPT,
                {"role": "user", "content": vision_content}
            ],
            "max_tokens": 2048,
            "temperature": 0.1
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload, timeout=120
        )

        if response.status_code != 200:
            return {"success": False, "error": f"OpenAI Error {response.status_code}: {response.text}"}

        result = response.json()
        ai_response_content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')

        try:
            data = json.loads(ai_response_content)
            if "raw_text" in data and "parsed_data" in data:
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": "AI response missing required keys.", "raw": ai_response_content}
        except json.JSONDecodeError as json_err:
            return {"success": False, "error": f"JSON Parse Error: {json_err}", "raw": ai_response_content}

    except Exception as e:
        logger.error(f"VC Vision Extraction Error: {e}")
        return {"success": False, "error": str(e)}


def extract_bl_data(api_key: str, base64_file: str, model: str) -> Dict[str, Any]:
    """Bill of Lading Extraction"""
    try:
        try:
            clean_b64 = utils.extract_base64_content(base64_file)
            if not clean_b64:
                return {"success": False, "error": "Invalid base64 provided"}

            base64_images = utils.extract_image(clean_b64)
        except Exception as conv_err:
            return {"success": False, "error": f"PDF Conversion failed: {str(conv_err)}"}

        if not base64_images:
            return {"success": False, "error": "Could not extract images from PDF"}

        vision_content: List[Dict[str, Any]] = [
            {"type": "text", "text": prompts.BL_EXTRACTION_USER}
        ]

        for img_b64 in base64_images:
            vision_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"
                }
            })

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompts.BL_EXTRACTION_SYSTEM},
                {"role": "user", "content": vision_content}
            ],
            "max_tokens": 4096,
            "temperature": 0
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180
        )

        if response.status_code != 200:
            return {"success": False, "error": f"OpenAI Error {response.status_code}: {response.text}"}

        result = response.json()

        if 'choices' not in result or not result['choices']:
            return {"success": False, "error": "No choices returned from OpenAI"}

        ai_response = result['choices'][0]['message']['content'].strip()

        if "```json" in ai_response:
            ai_response = ai_response.split("```json")[1].split("```")[0].strip()
        elif "```" in ai_response:
            ai_response = ai_response.split("```")[1].split("```")[0].strip()

        try:
            bl_data = json.loads(ai_response)
            return {"success": True, "extracted_bl": bl_data}
        except json.JSONDecodeError as json_err:
            return {"success": False, "error": f"JSON Parse Error: {json_err}", "raw": ai_response}

    except Exception as e:
        logger.error(f"BL Extraction Error: {e}")
        return {"success": False, "error": str(e)}

def extract_document(api_key: str, base64_file: str, model: str, system_prompt_b64: str, user_prompt_b64: str) -> Dict[str, Any]:
    """
    Generic extraction using dynamic prompts.
    """
    try:
        system_prompt = utils.decode_base64_string(system_prompt_b64)
        user_prompt = utils.decode_base64_string(user_prompt_b64)

        if not system_prompt or not user_prompt:
            return {"success": False, "error": "Invalid Base64 prompts provided. Could not decode."}

        clean_b64 = utils.extract_base64_content(base64_file)
        if not clean_b64:
            return {"success": False, "error": "Invalid base64 provided"}

        try:
            base64_images = utils.extract_image(clean_b64)
        except Exception as conv_err:
            return {"success": False, "error": f"PDF Conversion failed: {str(conv_err)}"}

        if not base64_images:
            return {"success": False, "error": "Could not extract images from PDF"}

        vision_content: List[Dict[str, Any]] = [
            {"type": "text", "text": user_prompt}
        ]

        for img_b64 in base64_images:
            vision_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"
                }
            })

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": vision_content}
            ],
            "max_tokens": 4096,
            "temperature": 0,
            "response_format": {"type": "json_object"}
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            return {"success": False, "error": f"OpenAI Error {response.status_code}: {response.text}"}

        result = response.json()

        if 'choices' not in result or not result['choices']:
            return {"success": False, "error": "No choices returned from OpenAI"}

        ai_response = result['choices'][0]['message']['content'].strip()

        try:
            extracted_data = json.loads(ai_response)
            cleaned_data = utils.clean_json_newlines(extracted_data)
            return {"success": True, "extracted_data": cleaned_data}
        except json.JSONDecodeError:
            if "```json" in ai_response:
                ai_response = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                ai_response = ai_response.split("```")[1].split("```")[0].strip()

            try:
                extracted_data = json.loads(ai_response)
                return {"success": True, "extracted_data": extracted_data}
            except json.JSONDecodeError as json_err:
                return {"success": False, "error": f"JSON Parse Error: {json_err}", "raw": ai_response}

    except Exception as e:
        logger.error(f"Generic Doc Error: {e}")
        return {"success": False, "error": str(e)}