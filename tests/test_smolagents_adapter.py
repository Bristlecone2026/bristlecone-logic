"""Unit tests verifying BristleconeScraperTool execution boundaries."""
import pytest
from unittest.mock import patch, MagicMock
from src.adapters.smolagents_adapter import BristleconeScraperTool
from src.security.socket_guard import SecurityException


def test_scraper_blocks_ssrf_attempt():
    tool = BristleconeScraperTool()
    # Attempting to query AWS/GCP cloud metadata IP
    with pytest.raises(SecurityException):
        tool.forward("http://169.254.169.254/latest/meta-data/")


@patch("src.security.socket_guard.SocketGuard.inspect_and_resolve")
def test_scraper_executes_sanitized_flow(mock_resolve):
    mock_resolve.return_value = "93.184.216.34"

    mock_handler = MagicMock()
    mock_handler.execute_request.return_value = {
        "status_code": 200,
        "headers": {},
        "body": b"<html><body><h1>Test Content</h1><p>Agent Payload Data</p></body></html>"
    }

    tool = BristleconeScraperTool(handler=mock_handler)
    result = tool.forward("https://example.com")

    assert "Test Content" in result
    assert "Agent Payload Data" in result
    assert "<html>" not in result
    mock_resolve.assert_called_once_with("example.com")
