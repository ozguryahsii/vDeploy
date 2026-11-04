"""python -m vdeploy  →  http://127.0.0.1:3031"""
import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "vdeploy.web:app",
        host=os.environ.get("VDEPLOY_HOST", "127.0.0.1"),
        port=int(os.environ.get("VDEPLOY_PORT", "3031")),
        reload=os.environ.get("VDEPLOY_RELOAD") == "1",
    )


if __name__ == "__main__":
    main()
