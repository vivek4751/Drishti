# At the top, add fallback
try:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
except:
    DEVICE = torch.device("cpu")

print(f"[ImageDetector] Using device: {DEVICE}")

def load_model():
    try:
        print("[ImageDetector] Loading Pre-trained Model...")
        model_name = "Organika/sdxl-detector"
        processor = AutoImageProcessor.from_pretrained(model_name)
        model = AutoModelForImageClassification.from_pretrained(model_name)
        model.to(DEVICE)
        model.eval()
        print(f"[ImageDetector] Model loaded on {DEVICE}")
        return model, processor
    except Exception as e:
        print(f"[ERROR] Model load failed: {e}")
        return None, None