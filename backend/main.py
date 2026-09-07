from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import os
import sys

app = FastAPI(
    title="Drishti Deepfake API",
    description="Multi-layer deepfake detection system"
)

# CORS - Allow all origins (for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("=" * 60)
print("🛡️ DRISHTI - Deepfake Detection API")
print("=" * 60)

# Load detectors
print("\n📦 Loading AI models...")
try:
    from audio_detector import AudioDeepfakeDetector
    audio_detector = AudioDeepfakeDetector()
    print("✅ Audio detector loaded")
except Exception as e:
    print(f"⚠️ Audio detector load failed: {e}")
    audio_detector = None

# Include routers
try:
    from routes.image import router as image_router
    app.include_router(image_router)
    print("✅ Image analyzer loaded")
except Exception as e:
    print(f"⚠️ Image analyzer load failed: {e}")

try:
    from routes.document import router as document_router
    app.include_router(document_router)
    print("✅ Document analyzer loaded")
except Exception as e:
    print(f"⚠️ Document analyzer load failed: {e}")

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {
        "status": "active",
        "service": "Drishti Deepfake Detection API",
        "version": "1.0.0",
        "endpoints": {
            "audio": "/analyze/audio",
            "image": "/analyze/image",
            "document": "/analyze/document"
        }
    }

@app.get("/health")
def health():
    """Simple health check"""
    return {"status": "ok"}

@app.post("/analyze/audio")
async def analyze_audio_endpoint(file: UploadFile = File(...)):
    """Analyze audio file for deepfake"""
    if not audio_detector:
        raise HTTPException(status_code=503, detail="Audio detector not loaded")
    
    if not file.filename:
        return {"verdict": "ERROR", "confidence": 0, "explanation": "No file uploaded"}
    
    import tempfile
    import shutil
    
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = tmp.name
    
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        result = audio_detector.analyze_audio(temp_path)
        return result
    except Exception as e:
        return {
            "verdict": "ERROR",
            "confidence": 0,
            "explanation": f"Server error: {str(e)}"
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

print("\n✅ API Ready! Starting server...\n")