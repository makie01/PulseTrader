# PulseTrade: LLM-Powered Prediction Market Trading System

PulseTrade is a multi-agent AI system that helps users discover, research, and trade on Kalshi prediction markets. The system uses Large Language Models (LLMs) to understand natural language market descriptions, conduct research, and execute trades.

## Features

- **Market Discovery**: Find relevant prediction markets using natural language queries
- **Research Agent**: Get in-depth analysis of markets with source-grounded research
- **Trade Execution**: Execute trades on Kalshi with explicit user confirmation
- **Cross-Platform Arbitrage**: Detect arbitrage opportunities between Kalshi and Polymarket

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Kalshi Package Modifications](#kalshi-package-modifications)
4. [API Keys Setup](#api-keys-setup)
5. [Running the Chatbot](#running-the-chatbot)
6. [Running the Arbitrage Finder](#running-the-arbitrage-finder)
7. [Usage Examples](#usage-examples)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.13 or above** installed (required by the `kalshi_python_sync` package)
- **pip** package manager
- **Google Cloud Platform (GCP) account** with Vertex AI API enabled
- **Kalshi account** with API credentials
- **Perplexity API key** (for Sonar Pro research - used directly via API)
- **Git** (to clone the repository)

---

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd PulseTrader
```

### 2. Verify Python Version

**Important**: This project requires Python 3.13 or above due to dependencies in the `kalshi_python_sync` package.

```bash
python3 --version
```

You should see something like `Python 3.13.x` or higher. If you have an older version, you'll need to upgrade Python before proceeding.

### 3. Create a Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 4. Install Required Packages

```bash
pip install -r requirements.txt
```

**Required packages:**
- `google-adk` - Google Agent Development Kit for multi-agent systems
- `kalshi_python_sync` - Kalshi API client (requires Python 3.13+ and modifications, see below)
- `python-dotenv` - Environment variable management
- `google-genai` - Google Gemini API client
- `perplexity` - Perplexity Sonar Pro API client
- `numpy`, `tqdm`, `requests`, `pandas` - Supporting libraries

---

## Kalshi Package Modifications

**Note**: The `kalshi_python_sync` package requires Python 3.13 or above. Make sure you're using the correct Python version before proceeding.

The `kalshi_python_sync` package is out of sync with the Kalshi API. You need to make the following modifications to fix compatibility issues.

### Locate the Package Installation

First, find where the package is installed:

```bash
python -c "import kalshi_python_sync; print(kalshi_python_sync.__file__)"
```

This will show you the path to the package. Typically it's in:
- `venv/lib/python3.X/site-packages/kalshi_python_sync/` (if using venv)
- Or `~/.local/lib/python3.X/site-packages/kalshi_python_sync/` (if installed globally)

### Modification 1: Add 'inactive' to Status Enum

**File**: `kalshi_python_sync/models/market.py`

**Location**: Around line 105-106 (in the `status_validate_enum` method)

**Change from:**
```python
if value not in set(['initialized', 'active', 'closed', 'settled', 'determined']):
    raise ValueError("must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined')")
```

**Change to:**
```python
if value not in set(['initialized', 'active', 'closed', 'settled', 'determined', 'inactive']):
    raise ValueError("must be one of enum values ('initialized', 'active', 'closed', 'settled', 'determined', 'inactive')")
```

### Modification 2: Make price_ranges Optional

**File**: `kalshi_python_sync/models/market.py`

**Step 2a - Add import (around line 28):**
```python
import warnings
```

**Step 2b - Change field type (around line 93):**

**Change from:**
```python
price_ranges: List[PriceRange] = Field(description="Valid price ranges for orders on this market")
```

**Change to:**
```python
price_ranges: Optional[List[PriceRange]] = Field(default=None, description="Valid price ranges for orders on this market")
```

**Step 2c - Update from_dict method (around line 304):**

**Change from:**
```python
"price_ranges": [PriceRange.from_dict(_item) for _item in obj["price_ranges"]] if obj.get("price_ranges") is not None else None
```

**Change to:**
```python
"price_ranges": [PriceRange.from_dict(_item) for _item in obj["price_ranges"]] if obj.get("price_ranges") is not None else (warnings.warn("Market " + str(obj.get("ticker", "unknown")) + " has price_ranges=None. This may indicate the market has no valid price ranges or the API returned incomplete data.", UserWarning) or None)
```

**Note**: Don't forget to add `Optional` to the imports at the top of the file if it's not already there:
```python
from typing import Optional, List
```

### Verification

After making these changes, verify the package still imports correctly:

```bash
python -c "from kalshi_python_sync import KalshiClient; print('Import successful!')"
```

---

## API Keys Setup

You need to set up several API keys and credentials for the system to work.

### 1. Create Environment File

Create a `.env` file in the project root directory:

```bash
touch .env
```

### 2. Google Cloud / Vertex AI Setup

The system uses Google's Gemini models via Vertex AI. You need:

1. **Enable Vertex AI API** in your GCP project
2. **Set up authentication** (either via `gcloud auth application-default login` or service account)
3. **Set environment variables** in your `.env` file:

```bash
# .env file
GOOGLE_GENAI_USE_VERTEXAI=True
GOOGLE_GENAI_PROJECT=your-gcp-project-id
GOOGLE_GENAI_LOCATION=us-central1  # or your preferred region
```

**Alternative**: If you're using Google API keys instead of Vertex AI, you can set:
```bash
GOOGLE_API_KEY=your-google-api-key
```

### 3. Kalshi API Credentials

1. **Get your Kalshi API credentials** from your Kalshi account settings
2. **Create a private key file**:
   - Save your Kalshi private key to `keys/llmfin.txt`
   - Make sure the `keys/` directory exists: `mkdir -p keys`
   - The file should contain your private key (PEM format)

3. **Add to `.env` file**:
```bash
KALSHI_API_KEY_ID=your-kalshi-api-key-id
```

**File structure should be:**
```
PulseTrader/
├── keys/
│   └── llmfin.txt          # Your Kalshi private key (PEM format)
├── .env                    # Environment variables
└── ...
```

### 4. Perplexity Sonar Pro API Key

**Note**: The system uses the Perplexity Sonar Pro API directly. You need a Perplexity API key to enable the research agent.

1. **Get a Perplexity API key** from [Perplexity API](https://www.perplexity.ai/settings/api)
2. **Add to `.env` file**:
```bash
PERPLEXITY_API_KEY_ID=your-perplexity-api-key
```

### 5. Complete `.env` File Example

Your `.env` file should look like this:

```bash
# Google Cloud / Vertex AI
GOOGLE_GENAI_USE_VERTEXAI=True
GOOGLE_GENAI_PROJECT=my-gcp-project
GOOGLE_GENAI_LOCATION=us-central1

# Kalshi API
KALSHI_API_KEY_ID=your-kalshi-api-key-id

# Perplexity Sonar Pro API (used directly)
PERPLEXITY_API_KEY_ID=your-perplexity-api-key
```

**Security Note**: Never commit your `.env` file or `keys/` directory to version control. They are already in `.gitignore`.

---

## Running the Chatbot

### Option 1: Using Google ADK Web UI (Recommended)

The easiest way to interact with the chatbot is through Google ADK's web interface.

#### Step 1: Navigate to the Project Root

Make sure you're in the project root directory (where `pred_market_agent/` folder is located):

```bash
cd PulseTrader  # or wherever you cloned the repository
```

#### Step 2: Run ADK Web

```bash
adk web
```

This will:
- Start a local web server
- Open your browser to the ADK web interface (typically at `http://localhost:8080`)
- Allow you to interact with the `pred_market_agent` through a chat interface

**Note**: Run `adk web` from the project root, not from inside the `pred_market_agent/` directory.

#### Step 3: Interact with the Agent

Once the web UI is open, you can:

1. **Discover Markets**: Ask questions like:
   - "Can you find me prediction markets related to US Politics?"
   - "Show me markets about the weather"
   - "Find markets related to sports"

2. **Research Markets**: After discovering markets, request research:
   - "Can you research whether Trump will balance the budget?"
   - "Do some research on the US national debt markets"

3. **Execute Trades**: When ready to trade:
   - "I want to buy 1 contract of NO on KXBALANCE-29 at 91 cents"
   - The agent will confirm before executing

### Option 2: Programmatic Usage

You can also import and use the agent programmatically:

```python
from pred_market.agent import root_agent

# The agent is now available as root_agent
# You can interact with it through ADK's programmatic interface
```

### Troubleshooting ADK Web

If `adk web` doesn't work:

1. **Check ADK installation**:
   ```bash
   pip show google-adk
   ```

2. **Verify you're in the correct directory**:
   ```bash
   pwd  # Should show .../PulseTrader (project root, not pred_market_agent/)
   ls   # Should show pred_market_agent/, tools/, requirements.txt, etc.
   ```

3. **Check for import errors**:
   ```bash
   python -c "from pred_market_agent.agent import root_agent; print('Import successful')"
   ```

4. **Verify environment variables are loaded**:
   ```bash
   python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('KALSHI_API_KEY_ID:', os.getenv('KALSHI_API_KEY_ID') is not None)"
   ```

---

## Running the Arbitrage Finder

The repo also includes a cross-platform arbitrage pipeline between **Kalshi** and **Polymarket** under the `arbitrage_finding/` package.

### 1. Run the end-to-end arbitrage pipeline

From the project root (`PulseTrader/`), run:

```bash
python -m arbitrage_finding.main
```

This script (`arbitrage_finding/main.py`) performs three main steps:

1. **Index setup and event similarity search**
   - Ensures Kalshi and Polymarket event/embedding indices exist on disk.
   - Finds similar cross-platform event pairs using embeddings.
   - Writes a capped list of candidate event pairs to:
     - `data/cross_platform_event_candidates.csv`
2. **Prompt generation for LLM evaluation**
   - Builds structured prompts describing each candidate pair (events + markets, no prices).
   - Saves them to:
     - `data/cross_platform_event_prompts.csv`
3. **LLM-based arbitrage compatibility checks**
   - Uses Gemini via `google-genai` to decide whether each pair **could** support arbitrage (structurally/semantically).
   - Writes results to:
     - `data/cross_platform_event_results.csv`

You can tweak how many pairs are processed and other settings by editing the constants at the top of `arbitrage_finding/main.py` (e.g. `TOP_K_EVENTS`, `PROMPT_MAX_PAIRS`, `LLM_MODEL`).

#### Using the precomputed example data

For reproducibility (e.g., matching the report / presentation results), you can also download a snapshot of the `data/` folder that was used to generate those results from Google Drive:

- **Google Drive link (precomputed `data/` folder)**: `<ADD_GOOGLE_DRIVE_LINK_HERE>`

After downloading, place the contents under the project’s `data/` directory (creating it if needed), so paths like `data/cross_platform_event_candidates.csv` and `data/cross_platform_event_results.csv` line up with the scripts above.

### 2. Check for live arbitrage with current prices

Once the pipeline above has produced `data/cross_platform_event_results.csv`, you can check for **actual** arbitrage opportunities at current market prices by running:

```bash
python arbitrage_finding/check_arbitrage_opportunities.py
```

This script:

- Loads only the event pairs where the LLM judged `could_have_arbitrage == true`.
- Fetches **fresh** markets/prices from Kalshi and Polymarket for the matched market pairs.
- Computes net cost and profit for two strategies (buy YES on one exchange / NO on the other), including Kalshi fees.
- Prints a detailed summary to the console.
- Saves all detected opportunities to:
  - `data/arbitrage_opportunities.csv`

This gives you a current snapshot of executable cross-exchange arbitrage (subject to liquidity and slippage) based on the latest prices.

### 3. Notebooks for exploring results

There are two helper notebooks in `arbitrage_finding/`:

- `arbitrage_opportunities_display.ipynb`: loads `data/arbitrage_opportunities.csv` (produced by `check_arbitrage_opportunities.py`) and provides a richer, notebook-based view of the concrete arbitrage opportunities.
- `check_arbitrage_opportunities.ipynb`: explores and inspects the LLM evaluation outputs from step 3 of the pipeline (`data/cross_platform_event_results.csv`), including the `could_have_arbitrage` flags and matched market pair JSON.

---

## Usage Examples

### Example 1: Discovering Markets

**User**: "Can you find me 5 different prediction markets related to US Politics?"

**Agent Response**: 
- Searches for relevant events using semantic search
- Retrieves all markets for each event
- Displays top 3 events in detail with:
  - Event title and ticker
  - Market tickers and prices
  - Close dates and rules
- Lists additional relevant events briefly

### Example 2: Researching a Market

**User**: "Can you do some research on whether Trump will balance the budget?"

**Agent Response**:
- Fetches market data for the event
- Queries Perplexity Sonar Pro for current information
- Provides:
  - Likelihood assessment (e.g., "NO outcome highly probable >99%")
  - Key factors affecting the outcome
  - Comparison with current market pricing
  - Trading recommendation with sources

### Example 3: Executing a Trade

**User**: "I want to buy 1 contract of NO on KXBALANCE-29 at 91 cents"

**Agent Response**:
- Validates the trade parameters
- Executes the trade on Kalshi
- Returns:
  - Order status (executed/canceled)
  - Order ID
  - Fill count and execution price
  - Fees charged

---

## Troubleshooting

### Common Issues

#### 1. Import Errors

**Error**: `ModuleNotFoundError: No module named 'pred_market_agent'`

**Solution**:
- Make sure you're running from the project root or have the project in your Python path
- Check that `pred_market_agent/` directory exists and contains `agent.py`

#### 2. API Key Errors

**Error**: `RuntimeError: PERPLEXITY_API_KEY_ID is not set in the environment`

**Solution**:
- Verify your `.env` file exists in the project root
- Check that environment variables are being loaded (the code uses `dotenv.load_dotenv()`)
- Ensure variable names match exactly (case-sensitive)

#### 3. Kalshi Authentication Errors

**Error**: `401 Unauthorized` or authentication failures

**Solution**:
- Verify `KALSHI_API_KEY_ID` is set correctly in `.env`
- Check that `keys/llmfin.txt` contains your private key
- Ensure the private key is in PEM format
- Verify your Kalshi API credentials are active

#### 4. Google Cloud / Vertex AI Errors

**Error**: `403 Permission Denied` or `Vertex AI API not enabled`

**Solution**:
- Enable Vertex AI API in your GCP project
- Verify `GOOGLE_GENAI_PROJECT` matches your project ID
- Check that authentication is set up (`gcloud auth application-default login`)
- Verify the service account has necessary permissions

#### 5. Kalshi Package Validation Errors

**Error**: `ValueError: must be one of enum values...` or `price_ranges` errors

**Solution**:
- Verify you've made all the required modifications to `kalshi_python_sync/models/market.py`
- Check that you modified the correct file (use `python -c "import kalshi_python_sync; print(kalshi_python_sync.__file__)"` to find it)
- Restart your Python environment after making changes

#### 6. ADK Web Not Starting

**Error**: `command not found: adk` or `adk: command not found`

**Solution**:
- Verify `google-adk` is installed: `pip install google-adk`
- Check that your virtual environment is activated
- Try running: `python -m google.adk.web` (if available)

#### 7. Agent Not Found in Web UI

**Error**: Agent doesn't appear in ADK web interface

**Solution**:
- Ensure you're running `adk web` from the project root directory (not from inside `pred_market/`)
- Check that `agent.py` exists and defines `root_agent`
- Verify the agent name matches what ADK expects

---

## Project Structure

```
PulseTrader/
├── pred_market_agent/        # Main agent directory
│   ├── agent.py              # Root agent definition
│   ├── prompt.py             # Root agent prompt
│   ├── init.py               # Package initialization
│   └── sub_agents/           # Sub-agent implementations
│       ├── get_events_agent/    # Market discovery
│       ├── research_agent/     # Research with Perplexity Sonar Pro API
│       └── trade_agent/         # Trade execution
├── tools/                    # Utility scripts
│   ├── kalshi_client.py      # Kalshi API client
│   ├── markets.py            # Market data fetching
│   └── ...
├── keys/                     # API keys (gitignored)
│   └── llmfin.txt            # Kalshi private key
├── data/                     # Data files (gitignored)
├── .env                      # Environment variables (gitignored)
├── requirements.txt          # Python dependencies
└── README.md                # This file
```

---

## Additional Resources

- [Google ADK Documentation](https://github.com/google/adk)
- [Kalshi API Documentation](https://trading-api.kalshi.com/)
- [Perplexity Sonar Pro API Documentation](https://docs.perplexity.ai/)

---

## Support

If you encounter issues not covered in this guide:

1. Check the [Troubleshooting](#troubleshooting) section
2. Verify all API keys and credentials are set correctly
3. Ensure all package modifications are applied
4. Check that your Python version is 3.13 or above (required by kalshi_python_sync package)

---

## License

[Add your license information here]
