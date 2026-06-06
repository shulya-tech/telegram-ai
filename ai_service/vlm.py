import torch
import easyocr
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import numpy as np
import io
import base64
import threading


class VisionModelWrapper:
    def __init__(self, model_id="Salesforce/blip-image-captioning-large"):
        self.model_id = model_id
        self.model = None
        self.processor = None
        self.ocr_reader = None
        self.load_lock = threading.Lock()

    def load(self):
        if self.model is not None:
            return
        with self.load_lock:
            if self.model is None:
                print(f"Loading vision model {self.model_id}...")
                self.processor = BlipProcessor.from_pretrained(self.model_id)
                self.model = BlipForConditionalGeneration.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                )
                self.model.eval()
                print("Loading OCR model...")
                self.ocr_reader = easyocr.Reader(['ru', 'en'], gpu=torch.cuda.is_available())
                print("Vision model loaded.")

    def analyze_image(self, image_base64: str) -> str:
        self.load()
        try:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data)).convert("RGB")

            # OCR: extract text from image
            image_np = np.array(image)
            ocr_results = self.ocr_reader.readtext(image_np, detail=0, paragraph=True)
            extracted_text = "\n".join(ocr_results).strip()

            # BLIP: general image description
            inputs = self.processor(image, return_tensors="pt").to(self.model.device)
            with torch.no_grad():
                output = self.model.generate(**inputs, max_new_tokens=128)
            caption = self.processor.decode(output[0], skip_special_tokens=True)

            parts = []
            if caption:
                parts.append(f"Description: {caption}")
            if extracted_text:
                parts.append(f"Text on image:\n{extracted_text}")

            return "\n".join(parts) if parts else ""
        except Exception as e:
            print(f"Error analyzing image: {e}")
            return "Failed to analyze image."

vlm_instance = VisionModelWrapper()
