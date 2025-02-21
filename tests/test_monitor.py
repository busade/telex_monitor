import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from app.main import app, monitor  
from unittest.mock import AsyncMock

# Use TestClient for FastAPI testing
client = TestClient(app)


@pytest.mark.asyncio
async def test_monitor_endpoint(mocker):
    """Test the /tick endpoint and verify background task execution"""

    # Mock the monitor_task function to prevent actual execution
    mock_monitor_task = mocker.patch("app.monitor_task", new_callable=AsyncMock)

    # Sample request payload
    payload = {
        "channel_id": "test-channel-123",
        "return_url": "https://example.com/webhook",
        "settings": [
            {
                "label": "database_url",
                "type": "text",
                "required": True,
                "default": "postgresql://user:password@db-host:5432/testdb"
            },
            {
                "label": "max_query_duration",
                "type": "number",
                "required": True,
                "default": 10
            },
            
        ]
    }

    # Send POST request to /tick
    response = client.post("/tick", json=payload)

    # Assertions
    assert response.status_code == 202  # Check if API responds correctly
    assert response.json() == {"status": "success"}  # Verify expected response
    mock_monitor_task.assert_called_once_with(payload)  # Ensure monitor_task was called
