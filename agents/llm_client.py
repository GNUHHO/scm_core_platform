import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request


class GeminiClient:
    """
    Production HTTP client for Google Gemini API with structured JSON output enforcement,
    markdown fence sanitization, and exponential backoff retry logic.
    """

    def __init__(self, api_key: str = None, default_model: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.default_model = default_model
        self.ssl_context = ssl._create_unverified_context()

    @staticmethod
    def _clean_json_text(raw_text: str) -> str:
        """Strip markdown code blocks if present around JSON payload."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def generate_json(
        self,
        system_instruction: str,
        user_content: dict,
        model: str = None,
        max_retries: int = 3,
    ) -> dict:
        target_model = model or self.default_model
        if not self.api_key:
            raise ValueError("Gemini API Key is not configured.")

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{target_model}:generateContent?key={self.api_key}"
        )

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(user_content, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(
                endpoint,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as response:
                    raw_data = json.loads(response.read().decode("utf-8"))
                    text_response = raw_data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(self._clean_json_text(text_response))
            except urllib.error.HTTPError as e:
                error_details = e.read().decode("utf-8")
                if e.code in (429, 500, 503) and attempt < max_retries:
                    wait_sec = 2 ** attempt
                    print(f"[GeminiClient] HTTP {e.code} encountered. Retrying in {wait_sec}s...")
                    time.sleep(wait_sec)
                    continue
                raise RuntimeError(f"Gemini API Error (HTTP {e.code}): {error_details}") from e
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                raise RuntimeError(f"Failed to execute Gemini request: {str(e)}") from e