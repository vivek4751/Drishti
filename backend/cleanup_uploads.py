"""Remove abandoned uploads; run when the stack is stopped."""
import time
from config import JOB_TTL, UPLOAD_DIR

def cleanup():
    cutoff, count = time.time() - JOB_TTL, 0
    for path in UPLOAD_DIR.glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            count += 1
    return count
if __name__ == "__main__":
    print(f"Removed {cleanup()} expired uploads")
