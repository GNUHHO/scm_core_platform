import json
import ssl
import urllib.request
import os

API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Lg3P1mr7TkrSX4nJKUzSQxomhNfk-qjLVS0PzYA24sBA")


def list_supported_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"{'Tên Endpoint':<35} | {'Mô tả ngắn'}")
            print("-" * 75)
            for m in data.get("models", []):
                # Chỉ lọc các mô hình tạo văn bản/JSON
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    model_id = m["name"].replace("models/", "")
                    disp_name = m.get("displayName", "")
                    print(f"{model_id:<35} | {disp_name}")
    except Exception as e:
        print(f"Lỗi: {e}")


if __name__ == "__main__":
    list_supported_models()