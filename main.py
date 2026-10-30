import threading
import time
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
load_dotenv()

def start_api() -> None:
    uvicorn.run(
        "src.app:app",
        host="127.0.0.1",
        port=8011,
        log_level="error",
        access_log=False,
    )

if __name__ == "__main__":
    # 1. Start server in background thread
    server_thread = threading.Thread(target=start_api, daemon=True)
    server_thread.start()

    time.sleep(1)  # Wait for the server to start

    # 2. Launch Main CLI Interface
    input("Press Enter to shut down the server...")