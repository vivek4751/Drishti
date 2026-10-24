import os
import cv2
import torch
import torch.nn as nn
import numpy as np
from PIL import Image
from torchvision import transforms
from facenet_pytorch import MTCNN
import timm
import base64

# Keep this architecture consistent with video_model_training/model.py.
class VideoDeepfakeModel(nn.Module):
    def __init__(self, sequence_length=15, lstm_hidden_size=512, lstm_layers=1, dropout=0.5):
        super(VideoDeepfakeModel, self).__init__()
        self.sequence_length = sequence_length
        self.feature_extractor = timm.create_model('tf_efficientnet_b4_ns', pretrained=False, num_classes=0)
        feature_dim = self.feature_extractor.num_features
        self.lstm = nn.LSTM(input_size=feature_dim, hidden_size=lstm_hidden_size, num_layers=lstm_layers, batch_first=True, dropout=dropout if lstm_layers > 1 else 0.0)
        self.classifier = nn.Sequential(
            nn.Linear(lstm_hidden_size, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 1)
        )

    def forward(self, x):
        batch_size, seq_length, c, h, w = x.size()
        x = x.view(batch_size * seq_length, c, h, w)
        features = self.feature_extractor(x)
        features = features.view(batch_size, seq_length, -1)
        lstm_out, _ = self.lstm(features)
        last_hidden_output = lstm_out[:, -1, :]
        out = self.classifier(last_hidden_output)
        return out

NUM_FRAMES_PER_SEQ = 15
MAX_CHUNKS_TO_ANALYZE = 40 # Analyze up to 40 continuous video chunks
FACE_SIZE = 299
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Loading inference on device: {DEVICE}")

mtcnn = MTCNN(keep_all=False, select_largest=True, post_process=False, device=DEVICE)

transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

_model = None

def get_model():
    global _model
    if _model is None:
        model_path = os.getenv("VIDEO_MODEL_PATH", os.path.join(
            os.path.dirname(__file__), "..", "video_model_training", "video_deepfake_model.pth"))
        if not os.path.isfile(model_path):
            raise RuntimeError("Trained video checkpoint missing; no prediction was produced")
        candidate = VideoDeepfakeModel(sequence_length=NUM_FRAMES_PER_SEQ).to(DEVICE)
        candidate.load_state_dict(torch.load(model_path, map_location=DEVICE, weights_only=True))
        candidate.eval()
        _model = candidate
    return _model

def analyze_video(video_path: str):
    """Classify sampled 15-frame blocks and return the highest fake score."""
    get_model()  # Fail before decoding if the trained checkpoint is missing.
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < NUM_FRAMES_PER_SEQ:
        cap.release()
        raise ValueError(f"Video is too short. Needs at least {NUM_FRAMES_PER_SEQ} frames.")

    # Start blocks about one second apart; cap coverage for long videos below.
    stride_frames = int(fps)


    start_frames = list(range(0, total_frames - NUM_FRAMES_PER_SEQ + 1, max(1, stride_frames)))

    # Spread the capped set of blocks across the video timeline.
    if len(start_frames) > MAX_CHUNKS_TO_ANALYZE:
        indices = np.linspace(0, len(start_frames) - 1, MAX_CHUNKS_TO_ANALYZE, dtype=int)
        start_frames = [start_frames[i] for i in indices]

    chunked_sequences = []

    for start_f in start_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)

        segment_faces = []
        last_good_face = None

        for _ in range(NUM_FRAMES_PER_SEQ):
            ret, frame = cap.read()
            if not ret:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            try:

                face = mtcnn(img)
                if face is not None:
                    face_array = face.permute(1, 2, 0).byte().cpu().numpy()
                    face_img = Image.fromarray(face_array)
                    face_img = face_img.resize((FACE_SIZE, FACE_SIZE))
                    last_good_face = transform(face_img)
            except Exception:
                pass  # Reuse the previous crop below if one is available.

            # Repeat the previous crop after a missed detection. This can mask motion.
            if last_good_face is not None:
                segment_faces.append(last_good_face)

        # Only keep full 15-frame continuous segments
        if len(segment_faces) == NUM_FRAMES_PER_SEQ:
            chunked_sequences.append(torch.stack(segment_faces))

    cap.release()

    if len(chunked_sequences) == 0:
        raise ValueError("No continuous face sequences could be detected in the video.")

    # Keep the GPU batch bounded even when many timeline segments are sampled.
    model = get_model()
    batch_size = max(1, int(os.getenv("VIDEO_INFERENCE_BATCH_SIZE", "1")))
    predictions = []
    with torch.no_grad():
        for offset in range(0, len(chunked_sequences), batch_size):
            batch = torch.stack(chunked_sequences[offset:offset + batch_size]).to(DEVICE)
            with torch.amp.autocast(device_type=DEVICE.type, enabled=DEVICE.type == 'cuda'):
                logits = model(batch)
            predictions.append(torch.sigmoid(logits).cpu().numpy().flatten())
    fake_probs = np.concatenate(predictions)

    # A single flagged block determines the verdict. The threshold is uncalibrated.
    DETECTION_THRESHOLD = 0.50

    max_fake_prob = float(np.max(fake_probs))
    avg_fake_prob = float(np.mean(fake_probs))


    verdict = "FAKE" if max_fake_prob >= DETECTION_THRESHOLD else "REAL"
    confidence = max_fake_prob if verdict == "FAKE" else (1.0 - max_fake_prob)

    print(f"Evaluated {len(chunked_sequences)} chunks across the whole video. Probabilities: {fake_probs}")

    heatmaps_base64 = []
    if verdict == "FAKE" and len(chunked_sequences) > 0:
        try:
            worst_idx = int(np.argmax(fake_probs))
            worst_chunk = chunked_sequences[worst_idx].unsqueeze(0).to(DEVICE).clone().detach()
            worst_chunk.requires_grad_(True)

            activations = []
            gradients = []

            def forward_hook(module, input, output):
                activations.append(output)

            def backward_hook(module, grad_in, grad_out):
                gradients.append(grad_out[0])

            target_layer = model.feature_extractor.conv_head
            handle_forward = target_layer.register_forward_hook(forward_hook)
            handle_backward = target_layer.register_full_backward_hook(backward_hook)

            with torch.enable_grad():
                if DEVICE.type == 'cuda':
                    # Initialize the CUDA backward path on this worker thread.
                    _dummy = torch.matmul(torch.ones(1, 1, device=DEVICE, requires_grad=True), torch.ones(1, 1, device=DEVICE))
                    _dummy.sum().backward()

                # cuDNN RNN backward pass explicitly requires the LSTM to be in training mode
                model.lstm.train()
                with torch.amp.autocast(device_type=DEVICE.type if DEVICE.type == 'cuda' else 'cpu', enabled=DEVICE.type=='cuda'):
                    model.zero_grad()
                    out_logits = model(worst_chunk)

                    out_logits.backward(torch.ones_like(out_logits))

                model.lstm.eval()

            handle_forward.remove()
            handle_backward.remove()

            if len(activations) > 0 and len(gradients) > 0:
                activations = activations[0]
                gradients = gradients[0]
                # activations/gradients shape: (sequence_length, channels, height, width) [15, C, H, W]

                frame_indices = list(range(15))
                mean_tensor = torch.tensor([0.485, 0.456, 0.406], device=DEVICE).view(3, 1, 1)
                std_tensor = torch.tensor([0.229, 0.224, 0.225], device=DEVICE).view(3, 1, 1)

                for f_idx in frame_indices:
                    if f_idx < activations.size(0):
                        act = activations[f_idx]
                        grad = gradients[f_idx]

                        # Global average pooling on gradients to get weights
                        weights = torch.mean(grad, dim=(1, 2), keepdim=True)
                        cam = torch.sum(weights * act, dim=0)
                        cam = torch.relu(cam)

                        cam_np = cam.detach().cpu().float().numpy()

                        if np.isnan(cam_np).any() or np.max(cam_np) == 0:
                            continue

                        cam_np = cam_np / np.max(cam_np)

                        # Brighten low activations for display. This is not a localization mask.
                        cam_np = np.power(cam_np, 0.4)

                        cam_resized = cv2.resize(cam_np, (FACE_SIZE, FACE_SIZE))

                        # Smooth the displayed heatmap.
                        cam_resized = cv2.GaussianBlur(cam_resized, (21, 21), 0)

                        # Hide low activations in the overlay.
                        cam_resized = np.where(cam_resized < 0.05, 0, cam_resized)
                        if np.max(cam_resized) > 0:
                            cam_resized = cam_resized / np.max(cam_resized)

                        cam_uint8 = np.uint8(255 * cam_resized)
                        heatmap = cv2.applyColorMap(cam_uint8, cv2.COLORMAP_JET)

                        orig_tensor = worst_chunk[0, f_idx].detach() * std_tensor + mean_tensor
                        orig_tensor = torch.clamp(orig_tensor, 0, 1)
                        orig_np = (orig_tensor.cpu().numpy() * 255).astype(np.uint8)
                        orig_np = np.transpose(orig_np, (1, 2, 0)) # H, W, C
                        orig_bgr = cv2.cvtColor(orig_np, cv2.COLOR_RGB2BGR)

                        # Cap overlay opacity at 0.70 so the face remains visible.
                        alpha = np.expand_dims(cam_resized, axis=-1) * 0.70
                        overlay = (heatmap * alpha + orig_bgr * (1.0 - alpha)).astype(np.uint8)

                        _, buffer = cv2.imencode('.jpg', overlay)
                        b64_str = base64.b64encode(buffer).decode('utf-8')
                        heatmaps_base64.append(f"data:image/jpeg;base64,{b64_str}")
        except Exception as e:
            import traceback
            trace_str = traceback.format_exc()
            print(f"FAILED TO GENERATE GRAD-CAM: {e}\n{trace_str}")
            # Keep the classification result if heatmap generation fails.

            # Return a visible error tile instead of a heatmap.
            msg = "Error during Heatmap GPU Sync"
            blank_img = np.zeros((FACE_SIZE, FACE_SIZE, 3), dtype=np.uint8)
            cv2.putText(blank_img, "GPU ERROR", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, buffer = cv2.imencode('.jpg', blank_img)
            heatmaps_base64.append(f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}")
            pass

    return {
        "verdict": verdict,
        "confidence": confidence,
        "probability": max_fake_prob,
        "timeline_average": avg_fake_prob,
        "heatmaps": heatmaps_base64
    }
