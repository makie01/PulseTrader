
Install requirements, but kalshi SDK is out of sync with the kalshi API. Have to adapt in kalshi_python_sync/models/market.py:

old = "        if value not in set(['initialized', 'active', 'closed', 'settled', 'determined']):\n            raise ValueError(\"must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined')\")\n"

new = "        if value not in set(['initialized', 'active', 'closed', 'settled', 'determined', 'inactive']):\n            raise ValueError(\"must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined', 'inactive')\")\n"