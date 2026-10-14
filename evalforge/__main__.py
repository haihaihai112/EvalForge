import uvicorn
import os

if __name__ == "__main__":
    from .config import load_env
    load_env()
    uvicorn.run("evalforge.app:create_app", factory=True, host="127.0.0.1", port=int(os.getenv("EVALFORGE_PORT", "8791")))
