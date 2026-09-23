from unittest.mock import patch
from riva_agent.__main__ import main


def test_main():
    with patch("uvicorn.run") as mock_run:
        main()
        mock_run.assert_called_once_with("riva_agent.api.gateway:app", host="0.0.0.0", port=8085)
