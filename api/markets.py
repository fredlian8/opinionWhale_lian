from http.server import BaseHTTPRequestHandler
import json
import traceback
import requests
from datetime import datetime
import os

# Configuration
API_KEY = os.environ.get("OPINION_API_KEY", "")
API_HOST = "https://proxy.opinion.trade:8443"
WHALE_THRESHOLD = 500

def api_request(endpoint, params=None):
    """Direct API request to Opinion"""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["x-api-key"] = API_KEY
    url = f"{API_HOST}{endpoint}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def fetch_markets_data():
    errors = []
    all_markets = []

    # Try to get markets using direct API call
    for page in range(1, 4):
        try:
            data = api_request("/markets", {"page": page, "limit": 20})

            if "error" in data:
                errors.append(f"Page {page}: {data['error']}")
                break

            # Try different response structures
            markets_list = None
            if isinstance(data, dict):
                if "result" in data and data["result"]:
                    if isinstance(data["result"], dict) and "list" in data["result"]:
                        markets_list = data["result"]["list"]
                    elif isinstance(data["result"], list):
                        markets_list = data["result"]
                elif "data" in data:
                    if isinstance(data["data"], list):
                        markets_list = data["data"]
                    elif isinstance(data["data"], dict) and "list" in data["data"]:
                        markets_list = data["data"]["list"]
                elif "markets" in data:
                    markets_list = data["markets"]
                elif "list" in data:
                    markets_list = data["list"]
            elif isinstance(data, list):
                markets_list = data

            if not markets_list:
                errors.append(f"Page {page}: Unknown response structure: {json.dumps(data)[:500]}")
                break

            all_markets.extend(markets_list)

        except Exception as e:
            errors.append(f"Page {page}: {str(e)}")
            break

    if not all_markets:
        return {
            "error": "No markets fetched",
            "errors": errors,
            "markets": [],
            "whales": [],
            "total_volume": 0,
            "whale_count": 0,
            "updated_at": datetime.now().isoformat()
        }

    processed_markets = []
    whales = []

    for m in all_markets[:20]:
        try:
            # Handle both dict and object-like responses
            if isinstance(m, dict):
                market_id = m.get("market_id") or m.get("id")
                market_title = m.get("market_title") or m.get("title") or m.get("question") or ""
                yes_token_id = m.get("yes_token_id") or m.get("yesTokenId")
                volume = float(m.get("volume", 0) or 0)
                status = m.get("status_enum") or m.get("status") or "Active"
            else:
                market_id = getattr(m, "market_id", None) or getattr(m, "id", None)
                market_title = getattr(m, "market_title", "") or getattr(m, "title", "")
                yes_token_id = getattr(m, "yes_token_id", None)
                volume = float(getattr(m, "volume", 0) or 0)
                status = getattr(m, "status_enum", "Active") or "Active"

            if not market_id:
                continue

            outcomes = []

            if yes_token_id:
                token_id = yes_token_id
                price = 0
                bid_depth = 0
                ask_depth = 0

                # Get price
                try:
                    price_data = api_request("/price", {"token_id": token_id})
                    if price_data and "result" in price_data and price_data["result"]:
                        price = float(price_data["result"].get("price", 0) or 0)
                except:
                    pass

                # Get orderbook
                try:
                    ob_data = api_request("/orderbook", {"token_id": token_id})
                    if ob_data and "result" in ob_data and ob_data["result"]:
                        bids = ob_data["result"].get("bids", []) or []
                        asks = ob_data["result"].get("asks", []) or []
                        for b in bids:
                            bid_depth += float(b.get("size", 0) or 0)
                        for a in asks:
                            ask_depth += float(a.get("size", 0) or 0)
                except:
                    pass

                bid_value = bid_depth * price if price > 0 else 0
                ask_value = ask_depth * (1 - price) if 0 < price < 1 else ask_depth * 0.5

                outcomes.append({
                    "title": "YES",
                    "token_id": str(token_id)[:20] + "...",
                    "price": price,
                    "bid_depth": bid_value,
                    "ask_depth": ask_value
                })

                if bid_value >= WHALE_THRESHOLD:
                    whales.append({
                        "market_id": market_id,
                        "market_title": market_title,
                        "outcome": "YES",
                        "side": "BUY",
                        "price": price,
                        "size": bid_depth,
                        "value": bid_value
                    })
                if ask_value >= WHALE_THRESHOLD:
                    whales.append({
                        "market_id": market_id,
                        "market_title": market_title,
                        "outcome": "YES",
                        "side": "SELL",
                        "price": price,
                        "size": ask_depth,
                        "value": ask_value
                    })

            if outcomes:
                processed_markets.append({
                    "market_id": market_id,
                    "title": market_title,
                    "volume": volume,
                    "status": status,
                    "outcomes": outcomes
                })
        except Exception as e:
            errors.append(f"Market processing: {str(e)}")
            continue

    whales.sort(key=lambda x: x["value"], reverse=True)

    return {
        "markets": processed_markets,
        "whales": whales,
        "total_volume": sum(m["volume"] for m in processed_markets),
        "whale_count": len(whales),
        "updated_at": datetime.now().isoformat(),
        "debug": {
            "total_fetched": len(all_markets),
            "processed": len(processed_markets),
            "errors": errors if errors else None
        }
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data = fetch_markets_data()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=30')
            self.end_headers()

            self.wfile.write(json.dumps(data).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            error_data = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            self.wfile.write(json.dumps(error_data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
