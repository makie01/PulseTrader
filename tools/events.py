from kalshi_client import get_kalshi_client
from pprint import pprint
import json
import csv
from datetime import datetime

# Initialize the API client
client = get_kalshi_client()

# -----------------------------
# Query Parameters (matching API docs)
# -----------------------------

limit = 200  
# Max is 200. Controls how many events per page.

cursor = None  
# Pagination cursor. Leave None for first page.

status = None  
# Possible values: "open", "closed", "settled". Leave None for all.

series_ticker = None  
# Filter for events in a specific series, e.g. "PRES_2028".

min_close_ts = None  
# Filter events where at least one market closes AFTER this timestamp.

with_nested_markets = False  
# True → include a "markets" array inside each event.

try:
    # -----------------------------
    # Call the Events API
    # -----------------------------
    api_response = client.get_events(
        limit=limit,
        cursor=cursor,
        status=status,
        series_ticker=series_ticker,
        min_close_ts=min_close_ts,
        with_nested_markets=with_nested_markets
    )

    print("The response of EventsApi->get_events:\n")

    # Save events to CSV file
    if api_response.events:
        print(f"Total events returned: {len(api_response.events)}")
        # Check if there's a cursor for pagination
        if hasattr(api_response, 'cursor') and api_response.cursor:
            print(f"Next page cursor: {api_response.cursor}")
        
        # Generate CSV filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"events_{timestamp}.csv"
        
        # Get all possible fields from events (in case different events have different fields)
        all_fields = set()
        for event in api_response.events:
            # Convert event to dict if it's an object
            if hasattr(event, '__dict__'):
                all_fields.update(event.__dict__.keys())
            elif isinstance(event, dict):
                all_fields.update(event.keys())
        
        # Define column order (prioritize common fields)
        field_order = ['event_ticker', 'series_ticker', 'title', 'sub_title', 'status', 'markets']
        # Add any other fields that aren't in the priority list
        for field in sorted(all_fields):
            if field not in field_order:
                field_order.append(field)
        
        # Write to CSV
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=field_order)
            writer.writeheader()
            
            for event in api_response.events:
                # Convert event to dictionary
                if hasattr(event, '__dict__'):
                    event_dict = event.__dict__.copy()
                elif isinstance(event, dict):
                    event_dict = event.copy()
                else:
                    # Try to convert using vars() or get attributes
                    event_dict = {}
                    for field in field_order:
                        if hasattr(event, field):
                            value = getattr(event, field)
                            event_dict[field] = value
                
                # Handle None values and complex objects
                row = {}
                for field in field_order:
                    value = event_dict.get(field, '')
                    # Convert None to empty string
                    if value is None:
                        row[field] = ''
                    # Convert complex objects (like markets list) to JSON string
                    elif isinstance(value, (list, dict)):
                        row[field] = json.dumps(value)
                    else:
                        row[field] = str(value)
                
                writer.writerow(row)
        
        print(f"\nEvents saved to {csv_filename}")
        
    else:
        print("No events returned.")

except Exception as e:
    print("Exception when calling EventsApi->get_events: %s\n" % e)
