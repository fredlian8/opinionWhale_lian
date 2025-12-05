#!/usr/bin/env python3
"""
Opinion Whale Tracker Backend
FastAPI 后端服务 - 提供市场数据和巨鲸监控 API
"""

import asyncio
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import json
from datetime import datetime

from opinion_clob_sdk import Client

# Configuration
API_KEY = os.environ.get("OPINION_API_KEY", "")
WHALE_THRESHOLD = 500

# Initialize FastAPI
app = FastAPI(
    title="Opinion Whale Tracker API",
    description="巨鲸监控平台后端 API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Models
class Outcome(BaseModel):
    title: str
    token_id: str
    price: float
    bid_depth: float
    ask_depth: float

class Market(BaseModel):
    market_id: int
    title: str
    volume: float
    status: str
    outcomes: List[Outcome]

class WhaleOrder(BaseModel):
    market_id: int
    market_title: str
    outcome: str
    side: str
    price: float
    size: float
    value: float

class MarketsResponse(BaseModel):
    markets: List[Market]
    whales: List[WhaleOrder]
    total_volume: float
    whale_count: int
    updated_at: str

# Global cache
cache = {
    "data": None,
    "updated_at": None
}

def get_opinion_client():
    return Client(
        host='https://proxy.opinion.trade:8443',
        apikey=API_KEY,
        chain_id=56,
        rpc_url='https://bsc-dataseed.binance.org',
        private_key='0x0000000000000000000000000000000000000000000000000000000000000001',
        multi_sig_addr='0x2f0c9ba178c669b8a21173bd83b267bd9200ad6d'
    )

def fetch_all_markets():
    """获取所有市场数据"""
    client = get_opinion_client()
    all_markets = []

    # 获取市场列表
    for page in range(1, 8):
        try:
            markets = client.get_markets(page=page, limit=20)
            if not markets.result.list:
                break
            all_markets.extend(markets.result.list)
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    return all_markets

def process_market(client, market) -> Optional[Market]:
    """处理单个市场，获取详细信息"""
    try:
        outcomes = []

        # 检查是否是二元市场
        if market.yes_token_id:
            # 二元市场
            token_id = market.yes_token_id
            price = 0
            bid_depth = 0
            ask_depth = 0

            try:
                price_data = client.get_latest_price(token_id=token_id)
                if price_data.result.price:
                    price = float(price_data.result.price)
            except:
                pass

            try:
                ob = client.get_orderbook(token_id=token_id)
                if ob.result.bids:
                    bid_depth = sum(float(b.size) for b in ob.result.bids)
                if ob.result.asks:
                    ask_depth = sum(float(a.size) for a in ob.result.asks)
            except:
                pass

            outcomes.append(Outcome(
                title="YES",
                token_id=token_id[:20] + "...",
                price=price,
                bid_depth=bid_depth * price,
                ask_depth=ask_depth * (1 - price) if price < 1 else ask_depth * 0.5
            ))

        else:
            # 分类市场 - 获取子市场
            try:
                cat = client.get_categorical_market(market_id=market.market_id)
                if cat.result.data and cat.result.data.child_markets:
                    for cm in cat.result.data.child_markets:
                        token_id = cm.yes_token_id
                        price = 0
                        bid_depth = 0
                        ask_depth = 0

                        if token_id:
                            try:
                                price_data = client.get_latest_price(token_id=token_id)
                                if price_data.result.price:
                                    price = float(price_data.result.price)
                            except:
                                pass

                            try:
                                ob = client.get_orderbook(token_id=token_id)
                                if ob.result.bids:
                                    bid_depth = sum(float(b.price) * float(b.size) for b in ob.result.bids)
                                if ob.result.asks:
                                    ask_depth = sum(float(a.price) * float(a.size) for a in ob.result.asks)
                            except:
                                pass

                        outcomes.append(Outcome(
                            title=cm.market_title,
                            token_id=token_id[:20] + "..." if token_id else "",
                            price=price,
                            bid_depth=bid_depth,
                            ask_depth=ask_depth
                        ))
            except Exception as e:
                print(f"Error processing categorical market {market.market_id}: {e}")

        if not outcomes:
            return None

        return Market(
            market_id=market.market_id,
            title=market.market_title,
            volume=float(market.volume) if market.volume else 0,
            status=market.status_enum or "Active",
            outcomes=outcomes
        )

    except Exception as e:
        print(f"Error processing market {market.market_id}: {e}")
        return None

def detect_whales(markets: List[Market], threshold: float = WHALE_THRESHOLD) -> List[WhaleOrder]:
    """检测大单"""
    whales = []

    for market in markets:
        for outcome in market.outcomes:
            # 检测买墙
            if outcome.bid_depth >= threshold:
                whales.append(WhaleOrder(
                    market_id=market.market_id,
                    market_title=market.title,
                    outcome=outcome.title,
                    side="BUY",
                    price=outcome.price,
                    size=outcome.bid_depth / outcome.price if outcome.price > 0 else 0,
                    value=outcome.bid_depth
                ))

            # 检测卖墙
            if outcome.ask_depth >= threshold:
                whales.append(WhaleOrder(
                    market_id=market.market_id,
                    market_title=market.title,
                    outcome=outcome.title,
                    side="SELL",
                    price=outcome.price,
                    size=outcome.ask_depth / (1 - outcome.price) if outcome.price < 1 else outcome.ask_depth,
                    value=outcome.ask_depth
                ))

    return sorted(whales, key=lambda x: x.value, reverse=True)

async def refresh_data():
    print(f"[{datetime.now()}] Refreshing data...")

    if not API_KEY:
        cache["data"] = MarketsResponse(
            markets=[],
            whales=[],
            total_volume=0,
            whale_count=0,
            updated_at=datetime.now().isoformat()
        )
        cache["updated_at"] = datetime.now()
        print("OPINION_API_KEY not set, served empty dataset")
        return

    client = get_opinion_client()
    raw_markets = fetch_all_markets()

    markets = []
    for m in raw_markets[:50]:  # 限制前50个市场以加快速度
        processed = process_market(client, m)
        if processed:
            markets.append(processed)

    whales = detect_whales(markets)
    total_volume = sum(m.volume for m in markets)

    cache["data"] = MarketsResponse(
        markets=markets,
        whales=whales,
        total_volume=total_volume,
        whale_count=len(whales),
        updated_at=datetime.now().isoformat()
    )
    cache["updated_at"] = datetime.now()

    print(f"[{datetime.now()}] Data refreshed: {len(markets)} markets, {len(whales)} whales")

# API Endpoints
@app.get("/")
async def root():
    return {"message": "Opinion Whale Tracker API", "status": "running"}

@app.get("/api/markets", response_model=MarketsResponse)
async def get_markets():
    """获取所有市场数据和巨鲸信息"""
    if cache["data"] is None:
        await refresh_data()

    return cache["data"]

@app.get("/api/markets/{market_id}")
async def get_market(market_id: int):
    """获取单个市场详情"""
    if cache["data"] is None:
        await refresh_data()

    for market in cache["data"].markets:
        if market.market_id == market_id:
            return market

    raise HTTPException(status_code=404, detail="Market not found")

@app.get("/api/whales")
async def get_whales(threshold: int = WHALE_THRESHOLD):
    """获取大单列表"""
    if cache["data"] is None:
        await refresh_data()

    whales = [w for w in cache["data"].whales if w.value >= threshold]
    return {"whales": whales, "count": len(whales)}

@app.get("/api/orderbook/{token_id}")
async def get_orderbook(token_id: str):
    """获取订单簿"""
    try:
        client = get_opinion_client()
        ob = client.get_orderbook(token_id=token_id)

        bids = [{"price": float(b.price), "size": float(b.size)} for b in (ob.result.bids or [])]
        asks = [{"price": float(a.price), "size": float(a.size)} for a in (ob.result.asks or [])]

        return {
            "bids": bids,
            "asks": asks,
            "bid_count": len(bids),
            "ask_count": len(asks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh")
async def force_refresh():
    """强制刷新数据"""
    await refresh_data()
    return {"message": "Data refreshed", "updated_at": cache["updated_at"].isoformat()}

@app.get("/api/stats")
async def get_stats():
    """获取统计数据"""
    if cache["data"] is None:
        await refresh_data()

    data = cache["data"]
    return {
        "total_markets": len(data.markets),
        "total_volume": data.total_volume,
        "whale_count": data.whale_count,
        "top_markets": [
            {"id": m.market_id, "title": m.title, "volume": m.volume}
            for m in sorted(data.markets, key=lambda x: x.volume, reverse=True)[:5]
        ],
        "updated_at": data.updated_at
    }

# Background task to refresh data periodically
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(refresh_data())

    # 启动定时刷新任务
    async def periodic_refresh():
        while True:
            await asyncio.sleep(60)  # 每60秒刷新一次
            try:
                await refresh_data()
            except Exception as e:
                print(f"Error in periodic refresh: {e}")

    if API_KEY:
        asyncio.create_task(periodic_refresh())

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
