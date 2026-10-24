"""Pretrained image classifier adapter; no fabricated forensic features."""
import hashlib
import io
import os
from datetime import datetime, timezone
from PIL import Image
import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

class ImageDeepfakeDetector:
    def __init__(self):
        self.model_name = os.getenv("IMAGE_MODEL", "Organika/sdxl-detector")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoImageProcessor.from_pretrained(self.model_name)
        self.model = AutoModelForImageClassification.from_pretrained(self.model_name)
        self.model.to(self.device).eval()
        labels = self.model.config.id2label
        matches = [int(i) for i, label in labels.items()
                   if str(label).lower() in {"artificial", "fake", "ai", "ai-generated"}]
        if len(matches) != 1 or len(labels) != 2:
            raise RuntimeError("Unrecognized image label map; refusing to guess class indices")
        self.fake_index = matches[0]

    def analyze(self, content):
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError("Image exceeds 25 megapixels")
            image = source.convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            probs = self.model(**inputs).logits.softmax(dim=-1)[0]
        probability = float(probs[self.fake_index].item())
        verdict = "FAKE" if probability >= 0.5 else "REAL"
        confidence = probability if verdict == "FAKE" else 1 - probability
        return {
            "status": "ok", "verdict": verdict, "confidence": confidence,
            "confidence_percent": round(confidence * 100, 1),
            "probability": probability, "model": self.model_name,
            "artifacts_detected": [],
            "explanation": "Pretrained image classifier output. The score is not a calibrated certainty, "
                           "and the classifier does not establish authenticity or localize manipulation.",
            "legal": {"file_hash_sha256": hashlib.sha256(content).hexdigest(),
                      "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                      "model_version": self.model_name},
        }
