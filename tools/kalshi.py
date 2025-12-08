from kalshi_python_sync import Configuration, KalshiClient


# Make API calls
balance = client.get_balance()
print(f"Balance: ${balance.balance / 100:.2f}")