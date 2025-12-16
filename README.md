
Install requirements, but kalshi SDK is out of sync with the kalshi API. Have to adapt in `kalshi_python_sync/models/market.py`:

## Change 1: Add 'inactive' to status enum validator

**Location:** Around line 105-106 (in the `status_validate_enum` method)

**Old:**
```python
if value not in set(['initialized', 'active', 'closed', 'settled', 'determined']):
    raise ValueError("must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined')")
```

**New:**
```python
if value not in set(['initialized', 'active', 'closed', 'settled', 'determined', 'inactive']):
    raise ValueError("must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined', 'inactive')")
```

## Change 2: Make price_ranges optional and add warning

**Location 1:** Line 28 - Add import
```python
import warnings
```

**Location 2:** Line 93 - Change field type
**Old:**
```python
price_ranges: List[PriceRange] = Field(description="Valid price ranges for orders on this market")
```

**New:**
```python
price_ranges: Optional[List[PriceRange]] = Field(default=None, description="Valid price ranges for orders on this market")
```

**Location 3:** Line 304 - Add warning in from_dict method
**Old:**
```python
"price_ranges": [PriceRange.from_dict(_item) for _item in obj["price_ranges"]] if obj.get("price_ranges") is not None else None
```

**New:**
```python
"price_ranges": [PriceRange.from_dict(_item) for _item in obj["price_ranges"]] if obj.get("price_ranges") is not None else (warnings.warn("Market " + str(obj.get("ticker", "unknown")) + " has price_ranges=None. This may indicate the market has no valid price ranges or the API returned incomplete data.", UserWarning) or None)
```

**Reason:** Some markets return `price_ranges=None` from the API, causing Pydantic validation errors. Making it optional allows these markets to be processed, and the warning helps identify which markets have this issue.
