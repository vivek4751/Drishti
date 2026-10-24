"""Lazy model loading: these modules are never imported by the API."""
from functools import lru_cache

@lru_cache(maxsize=3)
def detector(modality):
    if modality == "image":
        from image_detector import ImageDeepfakeDetector
        return ImageDeepfakeDetector()
    if modality == "audio":
        from audio_detector import AudioDeepfakeDetector
        return AudioDeepfakeDetector()
    if modality == "document":
        from document_detector import DocumentForensicDetector
        return DocumentForensicDetector()
    raise ValueError("Unsupported detector")

def analyze(modality, path, filename):
    if modality == "video":
        from video_inference import analyze_video
        result = analyze_video(str(path))
    elif modality == "audio":
        result = detector(modality).analyze_audio(str(path))
    elif modality == "document":
        result = detector(modality).analyze_document(path.read_bytes(), filename)
    else:
        result = detector(modality).analyze(path.read_bytes())
    if result.get("verdict") == "ERROR" or result.get("status") == "error":
        raise RuntimeError(result.get("explanation") or result.get("error") or "Inference failed")
    result.update(media_type=modality, filename=filename)
    return result
