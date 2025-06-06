import requests
import json
from datetime import datetime, timedelta

# Tradier API base URL - Defaulting to Production
TRADIER_API_BASE_URL = "https://api.tradier.com/v1/"

# IMPORTANT: Replace 'YOUR_TRADIER_ACCESS_TOKEN' with your actual Tradier access token.
# This token should be your PRODUCTION access token.
TRADIER_ACCESS_TOKEN = "J0bVBR60xoYQZw8tIEREcqVfcmfd"  # Replace with your production token

HEADERS = {
    "Authorization": f"Bearer {TRADIER_ACCESS_TOKEN}",
    "Accept": "application/json"
}

def get_underlying_quote_price(symbol):
    """
    Fetches the last price of the underlying stock.
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
            quote_data = quote_data[0] if isinstance(quote_data, list) else quote_data
            if quote_data and 'last' in quote_data:
                return float(quote_data['last'])
            else:
                print(f"Could not extract last price from quote: {quote_data}")
                return None
        elif 'symbol' in data.get('quotes', {}): # Alternative structure
            quote_data = data['quotes']
            if quote_data and 'last' in quote_data:
                return float(quote_data['last'])
            else:
                print(f"Could not extract last price from quote (alt structure): {quote_data}")
                return None
        else:
            print(f"Unexpected quote data structure for {symbol}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching quote price for {symbol}: {e}\nResponse: {response_content}")
        return None
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error processing quote price for {symbol}: {e}\nResponse: {response_content}")
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
    Fetches the option chain with greeks.
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

def find_atm_smv_vol(options, underlying_price):
    """
    Finds the SMV Vol for the at-the-money call and put option.
    Returns a dictionary {'call_smv': float, 'put_smv': float}
    """
    if not options or underlying_price is None:
        return {'call_smv': None, 'put_smv': None}

    atm_call = min([opt for opt in options if opt and opt.get('option_type') == 'call' and opt.get('strike') is not None and opt.get('strike') >= underlying_price], 
                   key=lambda x: x['strike'], default=None)
    if not atm_call: # If no calls >= underlying_price, take closest OTM call
         atm_call = max([opt for opt in options if opt and opt.get('option_type') == 'call' and opt.get('strike') is not None], 
                   key=lambda x: x['strike'], default=None)


    atm_put = max([opt for opt in options if opt and opt.get('option_type') == 'put' and opt.get('strike') is not None and opt.get('strike') <= underlying_price], 
                  key=lambda x: x['strike'], default=None)
    if not atm_put: # If no puts <= underlying_price, take closest OTM put
        atm_put = min([opt for opt in options if opt and opt.get('option_type') == 'put' and opt.get('strike') is not None], 
                  key=lambda x: x['strike'], default=None)


    call_smv = atm_call.get('greeks', {}).get('smv_vol') if atm_call else None
    put_smv = atm_put.get('greeks', {}).get('smv_vol') if atm_put else None
    
    return {'call_smv': call_smv, 'put_smv': put_smv, 'atm_call_strike': atm_call.get('strike') if atm_call else None, 'atm_put_strike': atm_put.get('strike') if atm_put else None}


if __name__ == "__main__":
    if TRADIER_ACCESS_TOKEN == "YOUR_TRADIER_ACCESS_TOKEN":
        print("Please replace 'YOUR_TRADIER_ACCESS_TOKEN' with your actual Tradier PRODUCTION access token.")
    else:
        symbol_to_test = "SPY"
        target_dte = 5  # Target Days To Expiration for IV5
        print(f"--- Approximating {target_dte}-Day IV (IV{target_dte}) for {symbol_to_test} ---")

        # 1. Get current underlying price
        underlying_price = get_underlying_quote_price(symbol_to_test)
        if underlying_price is None:
            print(f"Could not get underlying price for {symbol_to_test}. Cannot proceed.")
            exit()
        print(f"Current {symbol_to_test} Price: {underlying_price}")

        # 2. Get all option expirations
        expirations = get_option_expirations(symbol_to_test)
        if not expirations:
            print(f"No expiration dates found for {symbol_to_test}. Cannot proceed.")
            exit()

        # 3. Find the expiration date closest to target_dte (5 days)
        today = datetime.now().date()
        closest_expiration = None
        min_dte_diff = float('inf')

        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                if exp_date < today: # Skip past expirations
                    continue
                
                dte = (exp_date - today).days
                dte_diff = abs(dte - target_dte)

                if dte_diff < min_dte_diff:
                    min_dte_diff = dte_diff
                    closest_expiration = exp_str
                    actual_dte_of_closest = dte
                elif dte_diff == min_dte_diff and (closest_expiration is None or dte < actual_dte_of_closest) : # Prefer earlier date if diff is same
                    closest_expiration = exp_str
                    actual_dte_of_closest = dte


            except ValueError:
                print(f"Warning: Could not parse expiration date {exp_str}")
        
        if closest_expiration is None:
            print(f"Could not find a suitable future expiration date for {symbol_to_test}.")
            exit()
        
        print(f"\nSelected Expiration: {closest_expiration} (Actual DTE: {actual_dte_of_closest} days, Target DTE: {target_dte} days)")

        # 4. Fetch option chain for this expiration
        option_chain = get_option_chain_with_ivs(symbol_to_test, closest_expiration)
        if not option_chain:
            print(f"Could not retrieve option chain for {closest_expiration}. Cannot proceed.")
            exit()

        # 5. Find ATM SMV Vol
        atm_ivs = find_atm_smv_vol(option_chain, underlying_price)

        print("\n--- IV5 Approximation ---")
        if atm_ivs['call_smv'] is not None:
            print(f"  ATM Call ({atm_ivs['atm_call_strike']}) SMV Vol: {atm_ivs['call_smv']:.4f} (This can be used as IV{target_dte} proxy)")
        else:
            print(f"  Could not find ATM Call SMV Vol for {closest_expiration}.")
            
        if atm_ivs['put_smv'] is not None:
            print(f"  ATM Put ({atm_ivs['atm_put_strike']}) SMV Vol: {atm_ivs['put_smv']:.4f} (This can be used as IV{target_dte} proxy)")
        else:
            print(f"  Could not find ATM Put SMV Vol for {closest_expiration}.")

        # A common approach is to average the ATM call and put IVs if available
        if atm_ivs['call_smv'] is not None and atm_ivs['put_smv'] is not None:
            avg_atm_smv = (atm_ivs['call_smv'] + atm_ivs['put_smv']) / 2
            print(f"  Average ATM Call/Put SMV Vol: {avg_atm_smv:.4f} (Alternative IV{target_dte} proxy)")
        elif atm_ivs['call_smv'] is not None:
             print(f"  Using Call SMV Vol as proxy: {atm_ivs['call_smv']:.4f}")
        elif atm_ivs['put_smv'] is not None:
            print(f"  Using Put SMV Vol as proxy: {atm_ivs['put_smv']:.4f}")
        else:
            print(f"  No ATM SMV Vol found to approximate IV{target_dte}.")

        print(f"\nNote: This is an approximation using options expiring in {actual_dte_of_closest} days.")
        print("A more precise calculation would involve interpolating between two expirations that bracket the 5-day mark.")

