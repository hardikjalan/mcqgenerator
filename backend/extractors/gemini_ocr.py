import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# __file__ is: .../backend/extractors/gemini_ocr.py
# We need to go up THREE levels to reach the project root (mcqgenerator/)
# dirname(__file__)         -> .../backend/extractors
# dirname(dirname(__file__)) -> .../backend
# dirname x3                -> .../mcqgenerator  ← .env.local lives here
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    '.env.local'
)
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print(f"WARNING: GEMINI_API_KEY not found. Searched at: {env_path}")
else:
    print(f"INFO: GEMINI_API_KEY loaded successfully from: {env_path}")

# Initialise the new google-genai client
client = genai.Client(api_key=api_key) if api_key else None

# Use Flash 2.0 — fast and highly capable for OCR tasks
GEMINI_MODEL = "gemini-2.0-flash"

def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Sends image bytes to Gemini and returns extracted text.
    Returns an empty string on failure or if no text is found.
    """
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured. Cannot perform OCR.")

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Extract all readable text from this image accurately. "
                "Do not describe the image, just output the text. "
                "If there is no text, return an empty string.",
            ],
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Gemini OCR Error: {e}")

    return ""
