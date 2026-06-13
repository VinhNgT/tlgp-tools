import uvicorn
from .app import app

def main():
    """Starts the Uvicorn server for the FastAPI engine."""
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
