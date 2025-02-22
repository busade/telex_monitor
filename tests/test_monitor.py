from fastapi.testclient import TestClient
from main import app  # Ensure the correct import path to your FastAPI app
import pytest

client = TestClient(app)

def test_monitor():
    """Test the /tick endpoint to ensure background monitoring starts."""
    payload = {
        "channel_id": "12345",
        "return_url": "http://example.com/webhook",
        "settings": [
            {"label": "site", "type": "text", "required": True, "default": "https://postgres-monitor.onrender.com/"},
            {"label": "database_url", "type": "text", "required": True, "default": "postgresql://user:password@db-host:5432/yourdatabase"},
            {"label": "Interval", "type": "dropdown", "required": True, "default": "*/4 * * * *"}
        ],
    }

    response = client.post("/tick", json=payload)
    
    assert response.status_code == 202
    assert response.json() == {"status": "success"}

