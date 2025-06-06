import requests
import json
from datetime import datetime, timedelta

# Tradier API base URL - Defaulting to Production
TRADIER_API_BASE_URL = "https://api.tradier.com/v1/"

# IMPORTANT: Replace 'YOUR_TRADIER_ACCESS_TOKEN' with your actual Tradier access token.
# This token should be your PRODUCTION access token.
# Keep your access token secure and do not share it publicly.
TRADIER_ACCESS_TOKEN = "J0bVBR60xoYQZw8tIEREcqVfcmfd"  # Replace with your production token

# Standard headers for Tradier API requests
HEADERS = {
    "Authorization": f"Bearer {TRADIER_ACCESS_TOKEN}",
    "Accept": "application/json"
}

def get_underlying_quote(symbol):
    """
    Fetches a stock quote from the Tradier API.
    Endpoint: /markets/quotes
    """
    endpoint = f"{TRADIER_API_BASE_URL}markets/quotes"
    params = {"symbols": symbol, "greeks": "false"}
    response_content = None
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params)
        response_content = response.text
        response.raise_for_status()
        data = response.json()
        if 'quotes' in data and 'quote' in data['quotes']:
            quote_data = data['quotes']['quote']
            return quote_data[0] if isinstance(quote_data, list) else quote_data
        elif 'symbol' in data.get('quotes', {}):
             return data['quotes']
        else:
            print(f"Unexpected quote data structure for {symbol}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching quote for {symbol}: {e}\nResponse: {response_content}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON for {symbol} quote.\nResponse: {response_content}")
        return None

def get_historical_data(symbol, interval="daily", start_date_str=None, end_date_str=None):
    """
    Fetches historical OHLCV data for a given stock symbol.
    Endpoint: /markets/history
    """
    endpoint = f"{TRADIER_API_BASE_URL}markets/history"
    if start_date_str is None and end_date_str is None:
        end_date_dt = datetime.now()
        start_date_dt = end_date_dt - timedelta(days=10) # Default to last 10 calendar days
        end_date_str = end_date_dt.strftime('%Y-%m-%d')
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
    elif end_date_str is None:
        end_date_str = datetime.now().strftime('%Y-%m-%d')

    params = {"symbol": symbol, "interval": interval, "start": start_date_str, "end": end_date_str}
    response_content = None
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params)
        response_content = response.text
        response.raise_for_status()
        data = response.json()
        if 'history' in data and data['history'] and 'day' in data['history']:
            days_data = data['history']['day']
            return [days_data] if isinstance(days_data, dict) else days_data # Handle single day or list
        elif data.get('history') is None:
            print(f"No historical data found for {symbol} in range. Response: {data}")
            return []
        else:
            print(f"Unexpected historical data structure for {symbol}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching historical data for {symbol}: {e}\nResponse: {response_content}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON for {symbol} historical data.\nResponse: {response_content}")
        return None

def get_option_expirations(symbol):
    """
    Fetches option expiration dates.
    """
    endpoint = f"{TRADIER_API_BASE_URL}markets/options/expirations"
    params = {"symbol": symbol, "includeAllRoots": "true", "strikes": "false"}
    response_content = None
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params)
        response_content = response.text
        response.raise_for_status()
        data = response.json()
        if 'expirations' in data and 'date' in data['expirations']:
            dates = data['expirations']['date']
            return [dates] if isinstance(dates, str) else dates
        else:
            print(f"Unexpected expirations data structure for {symbol}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching option expirations for {symbol}: {e}\nResponse: {response_content}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON for {symbol} expirations.\nResponse: {response_content}")
        return None

def get_option_chain_with_ivs(symbol, expiration_date):
    """
    Fetches the option chain and extracts relevant IV metrics.
    """
    endpoint = f"{TRADIER_API_BASE_URL}markets/options/chains"
    params = {"symbol": symbol, "expiration": expiration_date, "greeks": "true"}
    response_content = None
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params)
        response_content = response.text
        response.raise_for_status()
        data = response.json()
        if 'options' in data and 'option' in data['options']:
            return data['options']['option']
        else:
            print(f"Unexpected option chain structure for {symbol} (exp: {expiration_date}): {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching option chain for {symbol} (exp: {expiration_date}): {e}\nResponse: {response_content}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON for {symbol} option chain.\nResponse: {response_content}")
        return None

def find_near_the_money_options(options, underlying_price, num_strikes_around=2):
    """
    Finds a few options near the at-the-money price.
    Returns a dictionary with 'calls' and 'puts' lists.
    """
    if not options or underlying_price is None:
        return {'calls': [], 'puts': []}

    # Separate calls and puts, ensuring they are not None and have a strike
    all_calls = sorted([opt for opt in options if opt and opt.get('option_type') == 'call' and opt.get('strike') is not None], key=lambda x: x['strike'])
    all_puts = sorted([opt for opt in options if opt and opt.get('option_type') == 'put' and opt.get('strike') is not None], key=lambda x: x['strike'])

    # Find the strike closest to the underlying price
    closest_call_strike = min(all_calls, key=lambda x: abs(x['strike'] - underlying_price), default=None)
    closest_put_strike = min(all_puts, key=lambda x: abs(x['strike'] - underlying_price), default=None)

    selected_calls = []
    if closest_call_strike:
        closest_call_idx = all_calls.index(closest_call_strike)
        start_idx = max(0, closest_call_idx - num_strikes_around)
        end_idx = min(len(all_calls), closest_call_idx + num_strikes_around + 1)
        selected_calls = all_calls[start_idx:end_idx]
        
    selected_puts = []
    if closest_put_strike:
        closest_put_idx = all_puts.index(closest_put_strike)
        start_idx = max(0, closest_put_idx - num_strikes_around)
        end_idx = min(len(all_puts), closest_put_idx + num_strikes_around + 1)
        selected_puts = all_puts[start_idx:end_idx]
        
    return {'calls': selected_calls, 'puts': selected_puts}


if __name__ == "__main__":
    if TRADIER_ACCESS_TOKEN == "YOUR_TRADIER_ACCESS_TOKEN":
        print("Please replace 'YOUR_TRADIER_ACCESS_TOKEN' with your actual Tradier PRODUCTION access token.")
    else:
        symbol_to_test = "SPY"
        print(f"--- Data for {symbol_to_test} ---")

        # 1. Get Underlying Quote to find current price for ATM selection
        underlying_quote = get_underlying_quote(symbol_to_test)
        underlying_last_price = None
        if underlying_quote and underlying_quote.get('last') is not None:
            underlying_last_price = float(underlying_quote.get('last'))
            print(f"\n--- Current Quote for {symbol_to_test} ---")
            print(f"  Last Price: {underlying_last_price}")
            print(f"  Change: {underlying_quote.get('change')}")
            print(f"  Volume: {underlying_quote.get('volume')}")
        else:
            print(f"Could not get underlying price for {symbol_to_test}. Option IVs might not be ATM.")
        
        # 2. Get Historical OHLCV Data
        print(f"\n--- Historical OHLCV Data for {symbol_to_test} (last ~5 trading days) ---")
        historical_data = get_historical_data(symbol_to_test) # Uses default date range
        if historical_data:
            print(f"Retrieved {len(historical_data)} historical data points.")
            for day_data in historical_data[-5:]: # Print the most recent 5
                if day_data:
                    print(f"  Date: {day_data.get('date')}, O: {day_data.get('open')}, H: {day_data.get('high')}, L: {day_data.get('low')}, C: {day_data.get('close')}, V: {day_data.get('volume')}")
        else:
            print(f"Could not retrieve historical data for {symbol_to_test}.")

        # 3. Get Option Expirations
        expirations = get_option_expirations(symbol_to_test)
        selected_expiration = None
        if expirations:
            # Select nearest future or current expiration
            valid_expirations = []
            for exp_str in expirations:
                try:
                    exp_date_obj = datetime.strptime(exp_str, '%Y-%m-%d')
                    if exp_date_obj.date() >= datetime.now().date():
                        valid_expirations.append(exp_str)
                except ValueError:
                    print(f"Warning: Could not parse expiration date {exp_str}")
            
            if valid_expirations:
                selected_expiration = valid_expirations[0] # Takes the soonest valid one
                print(f"\n--- Option IV Details for Expiration: {selected_expiration} ---")
            else:
                print(f"No future or current expiration dates found for {symbol_to_test}.")
                if expirations: selected_expiration = expirations[0] # Fallback for testing
        else:
            print(f"No option expirations found for {symbol_to_test}.")

        # 4. Get Option Chain and IVs if an expiration was selected
        if selected_expiration and underlying_last_price is not None:
            option_chain = get_option_chain_with_ivs(symbol_to_test, selected_expiration)
            if option_chain:
                print(f"Fetched {len(option_chain)} contracts for {selected_expiration}.")
                atm_options = find_near_the_money_options(option_chain, underlying_last_price, num_strikes_around=2)

                print("\nNear-the-Money Calls:")
                if atm_options['calls']:
                    for contract in atm_options['calls']:
                        greeks = contract.get('greeks', {})
                        print(f"  Strike: {contract.get('strike'):<7} Bid IV: {greeks.get('bid_iv', 0):.4f}, Ask IV: {greeks.get('ask_iv', 0):.4f}, Mid IV: {greeks.get('mid_iv', 0):.4f}, SMV: {greeks.get('smv_vol', 0):.4f}")
                else:
                    print("  No near-the-money calls found or data issue.")
                
                print("\nNear-the-Money Puts:")
                if atm_options['puts']:
                    for contract in atm_options['puts']:
                        greeks = contract.get('greeks', {})
                        print(f"  Strike: {contract.get('strike'):<7} Bid IV: {greeks.get('bid_iv', 0):.4f}, Ask IV: {greeks.get('ask_iv', 0):.4f}, Mid IV: {greeks.get('mid_iv', 0):.4f}, SMV: {greeks.get('smv_vol', 0):.4f}")
                else:
                    print("  No near-the-money puts found or data issue.")
            else:
                print(f"Could not retrieve option chain for {selected_expiration}.")
        elif not underlying_last_price:
             print("Skipping option chain IV details as underlying price is unavailable.")
        else:
            print("Skipping option chain IV details as no suitable expiration was found.")
