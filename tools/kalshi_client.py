from kalshi_python_sync import Configuration, KalshiClient
import dotenv
import os

def get_kalshi_client():
    dotenv.load_dotenv()
    # Configure the client
    config = Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2"
    )

    # For authenticated requests
    # Read private key from file
    with open("keys/llmfin.txt", "r") as f:
        private_key = f.read()

    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = private_key

    # Initialize the client
    client = KalshiClient(config)
    return client
