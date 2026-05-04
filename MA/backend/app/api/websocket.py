"""
WebSocket endpoints for real-time data streaming
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio
import logging
from typing import Dict, Set

from app.services.exchange_service import exchange_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel: str):
        """Connect a client to a channel"""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        logger.info(f"Client connected to channel: {channel}")
    
    def disconnect(self, websocket: WebSocket, channel: str):
        """Disconnect a client from a channel"""
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
            if not self.active_connections[channel]:
                del self.active_connections[channel]
        logger.info(f"Client disconnected from channel: {channel}")
    
    async def broadcast(self, channel: str, message: dict):
        """Broadcast message to all clients in a channel"""
        if channel not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.active_connections[channel].discard(conn)


manager = ConnectionManager()


@router.websocket("/market/{symbol:path}")
async def websocket_market_data(websocket: WebSocket, symbol: str):
    """WebSocket endpoint for real-time market data"""
    exchange = "binance"  # Default exchange
    channel = f"market_{symbol}_{exchange}"
    
    await manager.connect(websocket, channel)
    
    try:
        while True:
            # Fetch current ticker
            ticker = await exchange_service.fetch_ticker(symbol, exchange)
            
            if ticker:
                await websocket.send_json({
                    "type": "ticker",
                    "data": ticker
                })
            
            # Wait before next update (e.g., 5 seconds)
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, channel)


@router.websocket("/tickers")
async def websocket_multiple_tickers(websocket: WebSocket):
    """WebSocket endpoint for multiple tickers"""
    channel = "tickers_all"
    
    await manager.connect(websocket, channel)
    
    try:
        # Get symbols from client
        data = await websocket.receive_json()
        symbols = data.get("symbols", ["BTC/USDT", "ETH/USDT"])
        exchange = data.get("exchange", "binance")
        
        while True:
            # Fetch all tickers
            tickers = await exchange_service.fetch_multiple_tickers(symbols, exchange)
            
            if tickers:
                await websocket.send_json({
                    "type": "tickers",
                    "data": tickers
                })
            
            # Wait before next update
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, channel)


@router.websocket("/portfolio/{portfolio_id}")
async def websocket_portfolio(websocket: WebSocket, portfolio_id: int):
    """WebSocket endpoint for portfolio updates"""
    channel = f"portfolio_{portfolio_id}"
    
    await manager.connect(websocket, channel)
    
    try:
        # Send initial portfolio data
        # This would require importing database models, simplified here
        await websocket.send_json({
            "type": "portfolio_update",
            "message": "Connected to portfolio stream"
        })
        
        # Keep connection alive and send periodic updates
        while True:
            await asyncio.sleep(10)
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": asyncio.get_event_loop().time()
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, channel)

