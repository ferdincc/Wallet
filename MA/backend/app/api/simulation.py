"""
Simulation (Paper Trading) API endpoints
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict
from pydantic import BaseModel, field_validator
from datetime import datetime, timezone

from app.database import get_db
from app.models.portfolio import Portfolio, Transaction, Position, TransactionType, Order, OrderStatus
from app.models.user import User, RiskAppetite
from app.models.exchange_credentials import ExchangeCredentials, TradingMode
from app.services.exchange_service import exchange_service
from app.services.portfolio_rebalancing_service import portfolio_rebalancing_service
from app.agents.risk_agent import RiskAgent

router = APIRouter()
risk_agent = RiskAgent()
logger = logging.getLogger(__name__)


def ensure_simulation_user(db: Session, user_id: int) -> User:
    """
    Simülasyon UI sabit user_id (ör. 1) kullanır. Kullanıcı yoksa veritabanında oluşturur.
    Anahtarlar .env'de değil; ExchangeCredentials tablosunda saklanır.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user
    username = f"sim_user_{user_id}"
    email = f"sim_{user_id}@okyiss.local"
    try:
        user = User(
            id=user_id,
            username=username,
            email=email,
            risk_appetite=RiskAppetite.MODERATE,
            min_confidence_threshold=0.65,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Simülasyon kullanıcısı oluşturuldu: id=%s username=%s", user.id, user.username)
        return user
    except IntegrityError as e:
        db.rollback()
        logger.warning(
            "ensure_simulation_user IntegrityError user_id=%s: %s — yeniden sorgulanıyor",
            user_id,
            e,
        )
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
        user = db.query(User).filter(User.username == f"sim_user_{user_id}").first()
        if user:
            return user
        raise HTTPException(
            status_code=500,
            detail=f"Simülasyon kullanıcısı oluşturulamadı: {str(e.orig) if getattr(e, 'orig', None) is not None else str(e)}",
        ) from e


class PortfolioCreate(BaseModel):
    user_id: int
    name: str = "Default Portfolio"
    initial_balance: float = 10000.0


class TransactionCreate(BaseModel):
    portfolio_id: int
    symbol: str
    transaction_type: str  # Accept string, will convert to enum
    quantity: float
    exchange: str = "binance"
    limit_price: Optional[float] = None  # For limit orders


class PortfolioResponse(BaseModel):
    id: int
    user_id: int
    name: str
    initial_balance: float
    current_balance: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    portfolio_id: int
    symbol: str
    order_type: str  # "limit_buy" or "limit_sell"
    quantity: float
    limit_price: float
    exchange: str = "binance"


class RiskCheckRequest(BaseModel):
    portfolio_id: int
    symbol: str
    transaction_type: str  # Accept string, will convert to enum
    quantity: float
    price: float
    exchange: str = "binance"


@router.post("/portfolios", response_model=PortfolioResponse)
async def create_portfolio(portfolio: PortfolioCreate, db: Session = Depends(get_db)):
    """Create a new portfolio"""
    ensure_simulation_user(db, portfolio.user_id)
    
    db_portfolio = Portfolio(
        user_id=portfolio.user_id,
        name=portfolio.name,
        initial_balance=portfolio.initial_balance,
        current_balance=portfolio.initial_balance
    )
    
    db.add(db_portfolio)
    db.commit()
    db.refresh(db_portfolio)
    
    return db_portfolio


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    """Get portfolio details"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    return portfolio


@router.get("/portfolios")
async def list_portfolios(
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List portfolios"""
    query = db.query(Portfolio)
    
    if user_id:
        query = query.filter(Portfolio.user_id == user_id)
    
    portfolios = query.all()
    return {"portfolios": portfolios}


@router.post("/transactions/risk-check")
async def check_transaction_risk(risk_check: RiskCheckRequest, db: Session = Depends(get_db)):
    """Check risk before executing a transaction"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == risk_check.portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Convert string transaction_type to enum if needed
    if isinstance(risk_check.transaction_type, str):
        type_map = {
            'buy': TransactionType.BUY,
            'sell': TransactionType.SELL,
            'limit_buy': TransactionType.LIMIT_BUY,
            'limit_sell': TransactionType.LIMIT_SELL
        }
        risk_check.transaction_type = type_map.get(risk_check.transaction_type, TransactionType.BUY)
    
    # Calculate transaction value
    total_cost = risk_check.quantity * risk_check.price
    
    # Get current positions with actual prices (paralel; her ticker ayrı zaman aşımı)
    positions = db.query(Position).filter(Position.portfolio_id == risk_check.portfolio_id).all()

    async def _pos_value(pos):
        t = await exchange_service.fetch_ticker(pos.symbol, pos.exchange or "binance")
        return pos.quantity * t.get("price", 0) if t else 0.0

    if positions:
        parts = await asyncio.gather(*[_pos_value(p) for p in positions])
        total_position_value = sum(parts)
    else:
        total_position_value = 0.0
    
    total_portfolio_value = portfolio.current_balance + total_position_value
    
    # Risk checks
    warnings = []
    is_risky = False
    
    # Check 1: Position concentration (if buying)
    if risk_check.transaction_type in [TransactionType.BUY, TransactionType.LIMIT_BUY]:
        # Calculate new position size
        new_position_value = risk_check.quantity * risk_check.price
        new_total_value = total_portfolio_value + new_position_value
        position_pct = (new_position_value / new_total_value * 100) if new_total_value > 0 else 0
        
        if position_pct > 50:  # More than 50% in one asset
            is_risky = True
            warnings.append({
                "type": "position_concentration",
                "severity": "high",
                "message": f"Bu işlem portföyünüzün %{position_pct:.1f}'ini tek bir coine yatıracak. Bu çok riskli!",
                "position_percent": position_pct
            })
        
        # Check 2: Using too much balance
        balance_usage_pct = (total_cost / portfolio.current_balance * 100) if portfolio.current_balance > 0 else 0
        if balance_usage_pct > 80:
            is_risky = True
            warnings.append({
                "type": "high_balance_usage",
                "severity": "medium",
                "message": f"Bu işlem mevcut bakiyenizin %{balance_usage_pct:.1f}'ini kullanacak.",
                "balance_usage_percent": balance_usage_pct
            })
    
    # Check 3: Portfolio already has significant loss
    portfolio_loss = ((portfolio.current_balance - portfolio.initial_balance) / portfolio.initial_balance * 100)
    if portfolio_loss < -10:  # More than 10% loss
        warnings.append({
            "type": "portfolio_loss",
            "severity": "medium",
            "message": f"Portföyünüz %{abs(portfolio_loss):.1f} zararda. Yeni işlem yapmadan önce dikkatli olun.",
            "loss_percent": portfolio_loss
        })
    
    return {
        "is_risky": is_risky,
        "warnings": warnings,
        "warning_count": len(warnings),
        "transaction_value": total_cost,
        "portfolio_balance": portfolio.current_balance,
        "recommendation": "İşlemi iptal edin" if is_risky else "İşleme devam edebilirsiniz"
    }


@router.post("/transactions")
async def execute_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    """Execute a paper trade transaction (Market or Limit)"""
    # Get portfolio
    portfolio = db.query(Portfolio).filter(Portfolio.id == transaction.portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Convert string transaction_type to enum if needed
    if isinstance(transaction.transaction_type, str):
        type_map = {
            'buy': TransactionType.BUY,
            'sell': TransactionType.SELL,
            'limit_buy': TransactionType.LIMIT_BUY,
            'limit_sell': TransactionType.LIMIT_SELL
        }
        transaction_type_enum = type_map.get(transaction.transaction_type, TransactionType.BUY)
    else:
        transaction_type_enum = transaction.transaction_type
    
    # Handle limit orders
    if transaction_type_enum in [TransactionType.LIMIT_BUY, TransactionType.LIMIT_SELL]:
        if not transaction.limit_price or transaction.limit_price <= 0:
            raise HTTPException(status_code=400, detail="Limit price is required for limit orders")
        
        # Check balance/position for limit orders
        total_cost = transaction.quantity * transaction.limit_price
        
        if transaction_type_enum == TransactionType.LIMIT_BUY:
            if portfolio.current_balance < total_cost:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance. Required: ${total_cost:.2f}, Available: ${portfolio.current_balance:.2f}"
                )
            # Reserve balance for limit buy
            portfolio.current_balance -= total_cost
        else:  # LIMIT_SELL
            position = db.query(Position).filter(
                Position.portfolio_id == transaction.portfolio_id,
                Position.symbol == transaction.symbol
            ).first()
            
            if not position or position.quantity < transaction.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient position. You don't have enough {transaction.symbol} to sell"
                )
        
        # Create pending order
        order = Order(
            portfolio_id=transaction.portfolio_id,
            symbol=transaction.symbol,
            order_type=transaction_type_enum,
            quantity=transaction.quantity,
            limit_price=transaction.limit_price,
            status=OrderStatus.PENDING,
            exchange=transaction.exchange
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        
        return {
            "order": order,
            "message": "Limit order created. It will execute when price reaches the limit.",
            "portfolio": portfolio
        }
    
    # Handle market orders (existing logic)
    # Get current price
    ticker = await exchange_service.fetch_ticker(transaction.symbol, transaction.exchange)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Ticker not found for {transaction.symbol}")
    
    current_price = ticker.get("price", 0)
    if current_price <= 0:
        raise HTTPException(status_code=400, detail="Invalid price")
    
    total_cost = transaction.quantity * current_price
    
    # Check balance for buy orders
    if transaction_type_enum == TransactionType.BUY:
        if portfolio.current_balance < total_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Required: ${total_cost:.2f}, Available: ${portfolio.current_balance:.2f}"
            )
        portfolio.current_balance -= total_cost
    else:  # SELL
        # Check if position exists
        position = db.query(Position).filter(
            Position.portfolio_id == transaction.portfolio_id,
            Position.symbol == transaction.symbol
        ).first()
        
        if not position or position.quantity < transaction.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient position. You don't have enough {transaction.symbol} to sell"
            )
        
        portfolio.current_balance += total_cost
    
    # Create transaction record
    db_transaction = Transaction(
        portfolio_id=transaction.portfolio_id,
        symbol=transaction.symbol,
        transaction_type=transaction_type_enum,
        quantity=transaction.quantity,
        price=current_price,
        total=total_cost,
        exchange=transaction.exchange
    )
    db.add(db_transaction)
    
    # Update or create position
    position = db.query(Position).filter(
        Position.portfolio_id == transaction.portfolio_id,
        Position.symbol == transaction.symbol
    ).first()
    
    if transaction_type_enum == TransactionType.BUY:
        if position:
            # Update existing position
            total_cost_old = position.quantity * (position.avg_buy_price or 0)
            total_cost_new = transaction.quantity * current_price
            total_quantity = position.quantity + transaction.quantity
            position.avg_buy_price = (total_cost_old + total_cost_new) / total_quantity if total_quantity > 0 else current_price
            position.quantity = total_quantity
        else:
            # Create new position
            position = Position(
                portfolio_id=transaction.portfolio_id,
                symbol=transaction.symbol,
                quantity=transaction.quantity,
                avg_buy_price=current_price,
                exchange=transaction.exchange
            )
            db.add(position)
    else:  # SELL
        if position:
            position.quantity -= transaction.quantity
            if position.quantity <= 0:
                db.delete(position)
    
    db.commit()
    db.refresh(db_transaction)
    db.refresh(portfolio)
    
    return {
        "transaction": db_transaction,
        "portfolio": portfolio
    }


@router.get("/portfolios/{portfolio_id}/positions")
async def get_positions(portfolio_id: int, db: Session = Depends(get_db)):
    """Get all positions in a portfolio"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    positions = db.query(Position).filter(Position.portfolio_id == portfolio_id).all()

    async def _enrich(position):
        ticker = await exchange_service.fetch_ticker(position.symbol, position.exchange)
        current_price = ticker.get("price", 0) if ticker else 0
        position_value = position.quantity * current_price
        unrealized_pnl = 0
        unrealized_pnl_percent = 0
        if position.avg_buy_price and current_price > 0:
            unrealized_pnl = (current_price - position.avg_buy_price) * position.quantity
            unrealized_pnl_percent = ((current_price - position.avg_buy_price) / position.avg_buy_price) * 100
        return {
            "id": position.id,
            "symbol": position.symbol,
            "quantity": position.quantity,
            "avg_buy_price": position.avg_buy_price,
            "current_price": current_price,
            "position_value": position_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_percent": unrealized_pnl_percent,
            "exchange": position.exchange,
        }

    enriched_positions = await asyncio.gather(*[_enrich(p) for p in positions]) if positions else []
    return {"positions": enriched_positions}


@router.get("/portfolios/{portfolio_id}/transactions")
async def get_transactions(portfolio_id: int, db: Session = Depends(get_db)):
    """Get transaction history for a portfolio"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    transactions = db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio_id
    ).order_by(Transaction.timestamp.desc()).all()
    
    return {"transactions": transactions}


@router.get("/portfolios/{portfolio_id}/risk")
async def get_portfolio_risk(portfolio_id: int, db: Session = Depends(get_db)):
    """Get risk analysis for a portfolio"""
    result = await risk_agent.execute(portfolio_id=portfolio_id, db=db)
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    
    return result


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None


class UserUpdate(BaseModel):
    risk_appetite: Optional[str] = None  # "conservative", "moderate", "aggressive" veya MODERATE
    min_confidence_threshold: Optional[float] = None

    @field_validator("risk_appetite", mode="before")
    @classmethod
    def normalize_risk_appetite_input(cls, v):
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return None
        s = str(v).strip()
        low = s.lower()
        if low == "medium":
            return RiskAppetite.MODERATE.value
        if low in ("conservative", "moderate", "aggressive"):
            return low
        up = s.upper()
        if up in RiskAppetite.__members__:
            return RiskAppetite[up].value
        return low


@router.post("/users")
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    risk_appetite = RiskAppetite.MODERATE  # Default
    
    db_user = User(
        username=user.username,
        email=user.email,
        risk_appetite=risk_appetite,
        min_confidence_threshold=0.65,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


@router.patch("/users/{user_id}")
async def update_user_profile(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db)
):
    """Update user profile (risk appetite)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_update.risk_appetite:
        try:
            user.risk_appetite = RiskAppetite(user_update.risk_appetite)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid risk_appetite. Must be: conservative, moderate, aggressive")
    
    if user_update.min_confidence_threshold is not None:
        user.min_confidence_threshold = user_update.min_confidence_threshold
    
    db.commit()
    db.refresh(user)
    
    return user


@router.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get user details"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/orders")
async def create_limit_order(order: OrderCreate, db: Session = Depends(get_db)):
    """Create a limit order"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == order.portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Convert string order_type to enum
    type_map = {
        'limit_buy': TransactionType.LIMIT_BUY,
        'limit_sell': TransactionType.LIMIT_SELL
    }
    order_type_enum = type_map.get(order.order_type)
    if not order_type_enum:
        raise HTTPException(status_code=400, detail="Order type must be 'limit_buy' or 'limit_sell'")
    
    # Check balance for limit buy orders
    if order_type_enum == TransactionType.LIMIT_BUY:
        total_cost = order.quantity * order.limit_price
        if portfolio.current_balance < total_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Required: ${total_cost:.2f}, Available: ${portfolio.current_balance:.2f}"
            )
        # Reserve balance for limit buy
        portfolio.current_balance -= total_cost
    
    # Check position for limit sell orders
    elif order_type_enum == TransactionType.LIMIT_SELL:
        position = db.query(Position).filter(
            Position.portfolio_id == order.portfolio_id,
            Position.symbol == order.symbol
        ).first()
        
        if not position or position.quantity < order.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient position. You don't have enough {order.symbol} to sell"
            )
    
    # Create order
    db_order = Order(
        portfolio_id=order.portfolio_id,
        symbol=order.symbol,
        order_type=order_type_enum,
        quantity=order.quantity,
        limit_price=order.limit_price,
        status=OrderStatus.PENDING,
        exchange=order.exchange
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return db_order


@router.get("/portfolios/{portfolio_id}/orders")
async def get_orders(portfolio_id: int, db: Session = Depends(get_db)):
    """Get all orders for a portfolio"""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    orders = db.query(Order).filter(Order.portfolio_id == portfolio_id).order_by(Order.created_at.desc()).all()
    return {"orders": orders}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """Cancel a pending order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending orders can be cancelled")
    
    # Refund balance if it was a limit buy
    if order.order_type == TransactionType.LIMIT_BUY:
        portfolio = db.query(Portfolio).filter(Portfolio.id == order.portfolio_id).first()
        if portfolio:
            refund_amount = order.quantity * order.limit_price
            portfolio.current_balance += refund_amount
    
    order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    
    return order


@router.post("/orders/process")
async def process_pending_orders(portfolio_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Process pending limit orders (check if prices reached)"""
    query = db.query(Order).filter(Order.status == OrderStatus.PENDING)
    
    if portfolio_id:
        query = query.filter(Order.portfolio_id == portfolio_id)
    
    pending_orders = query.all()
    processed = []

    tickers = (
        await asyncio.gather(
            *[exchange_service.fetch_ticker(o.symbol, o.exchange) for o in pending_orders]
        )
        if pending_orders
        else []
    )

    for order, ticker in zip(pending_orders, tickers):
        if not ticker:
            continue

        current_price = ticker.get("price", 0)
        if current_price <= 0:
            continue

        should_execute = False

        if order.order_type == TransactionType.LIMIT_BUY:
            should_execute = current_price <= order.limit_price
        elif order.order_type == TransactionType.LIMIT_SELL:
            should_execute = current_price >= order.limit_price

        if should_execute:
            # Execute order as market transaction
            transaction = TransactionCreate(
                portfolio_id=order.portfolio_id,
                symbol=order.symbol,
                transaction_type=TransactionType.BUY if order.order_type == TransactionType.LIMIT_BUY else TransactionType.SELL,
                quantity=order.quantity,
                exchange=order.exchange
            )
            
            # Execute transaction (reuse existing logic)
            result = await execute_transaction(transaction, db)
            
            # Update order status
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_at = datetime.utcnow()
            db.commit()
            
            processed.append({
                "order_id": order.id,
                "status": "filled",
                "filled_price": current_price
            })
    
    return {
        "processed_count": len(processed),
        "processed_orders": processed
    }


# ==================== Real Exchange Integration ====================

class ExchangeCredentialsCreate(BaseModel):
    user_id: int
    exchange: str  # binance, coinbasepro, kraken
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None  # For Coinbase Pro
    trading_mode: str = "read_only"  # İstekte read_only | real_trading gelebilir; simülasyon her zaman READ_ONLY kaydeder


class ExchangeCredentialsResponse(BaseModel):
    id: int
    user_id: int
    exchange: str
    trading_mode: str
    is_active: bool
    created_at: datetime
    message: str = "API anahtarları kaydedildi (harici borsa doğrulaması yapılmadı)."

    class Config:
        from_attributes = True


@router.post("/exchange-credentials", response_model=ExchangeCredentialsResponse)
async def create_exchange_credentials(
    credentials: ExchangeCredentialsCreate, 
    db: Session = Depends(get_db)
):
    """
    API anahtarlarını yalnızca veritabanına yazar.
    Binance veya diğer borsalara bağlanıp doğrulama yapılmaz (hızlı kayıt, zaman aşımı yok).
    """
    logger.info(
        "exchange-credentials kaydı: user_id=%s exchange=%s mode=%s (key uzunlukları: %s / %s)",
        credentials.user_id,
        credentials.exchange,
        credentials.trading_mode,
        len(credentials.api_key or ""),
        len(credentials.api_secret or ""),
    )
    try:
        ensure_simulation_user(db, credentials.user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ensure_simulation_user başarısız: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        TradingMode(credentials.trading_mode)
    except ValueError:
        logger.error("Geçersiz trading_mode: %r", credentials.trading_mode)
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz trading_mode: {credentials.trading_mode}. read_only veya real_trading olmalı.",
        ) from None

    # Simülasyon / İzleme: gerçek işlem modu kaldırıldı; her zaman sadece okuma
    mode = TradingMode.READ_ONLY

    # Check if credentials already exist for this exchange
    existing = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == credentials.user_id,
        ExchangeCredentials.exchange == credentials.exchange.lower()
    ).first()
    
    if existing:
        # Update existing credentials
        existing.api_key = credentials.api_key
        existing.api_secret = credentials.api_secret
        existing.passphrase = credentials.passphrase
        existing.trading_mode = mode
        existing.is_active = True
    else:
        # Create new credentials
        existing = ExchangeCredentials(
            user_id=credentials.user_id,
            exchange=credentials.exchange.lower(),
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            passphrase=credentials.passphrase,
            trading_mode=mode,
            is_active=True
        )
        db.add(existing)

    try:
        db.commit()
        db.refresh(existing)
    except Exception as e:
        db.rollback()
        logger.exception("exchange-credentials DB commit hatası: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"API anahtarları veritabanına yazılamadı: {e!s}",
        ) from e

    logger.info("exchange-credentials kaydedildi: id=%s user_id=%s exchange=%s", existing.id, existing.user_id, existing.exchange)
    tm = existing.trading_mode
    trading_mode_str = tm.value if isinstance(tm, TradingMode) else str(tm)
    return ExchangeCredentialsResponse(
        id=existing.id,
        user_id=existing.user_id,
        exchange=existing.exchange,
        trading_mode=trading_mode_str,
        is_active=existing.is_active if existing.is_active is not None else True,
        created_at=existing.created_at or datetime.now(timezone.utc),
        message="API anahtarları kaydedildi (harici borsa doğrulaması yapılmadı).",
    )


@router.get("/exchange-credentials")
async def list_exchange_credentials(
    user_id: int,
    db: Session = Depends(get_db)
):
    """List exchange credentials for a user"""
    credentials = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == user_id,
        ExchangeCredentials.is_active == True
    ).all()
    
    return {
        "credentials": [
            {
                "id": cred.id,
                "exchange": cred.exchange,
                "trading_mode": cred.trading_mode.value,
                "is_active": cred.is_active,
                "created_at": cred.created_at
            }
            for cred in credentials
        ]
    }


@router.delete("/exchange-credentials/{credential_id}")
async def delete_exchange_credentials(
    credential_id: int,
    user_id: int = Query(..., description="Must match the credential owner"),
    db: Session = Depends(get_db),
):
    """Deactivate credentials and wipe secrets so they cannot be recovered from this row."""
    try:
        ensure_simulation_user(db, user_id)
    except HTTPException:
        raise

    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.id == credential_id
    ).first()

    if not credential:
        raise HTTPException(status_code=404, detail="Credentials not found")

    if credential.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to remove this credential")

    credential.is_active = False
    credential.api_key = ""
    credential.api_secret = ""
    credential.passphrase = None
    db.commit()

    return {"message": "Credentials removed", "ok": True}


@router.get("/real-exchange/balance")
async def get_real_exchange_balance(
    user_id: int,
    exchange: str,
    db: Session = Depends(get_db)
):
    """Get real exchange balance (Read-Only)"""
    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == user_id,
        ExchangeCredentials.exchange == exchange.lower(),
        ExchangeCredentials.is_active == True
    ).first()
    
    if not credential:
        raise HTTPException(status_code=404, detail="Exchange credentials not found")
    
    balance = await exchange_service.fetch_balance(
        credential.exchange,
        credential.api_key,
        credential.api_secret,
        credential.passphrase
    )
    
    if not balance:
        tech = (exchange_service.pop_last_private_error() or "").strip()
        if tech:
            detail_msg = (
                "Borsadan spot bakiyesi alınamadı. Kontrol: API 'Enable Reading', IP kısıtı, "
                "sistem saati; sunucu recvWindow=60s ve zaman senkronu kullanıyor. Detay: "
                + tech[:1800]
            )
        else:
            detail_msg = (
                "Borsadan bakiye alınamadı (zaman aşımı veya ağ). Anahtarları ve bağlantıyı kontrol edin."
            )
        raise HTTPException(status_code=504, detail=detail_msg)
    
    return balance


@router.get("/real-exchange/positions")
async def get_real_exchange_positions(
    user_id: int,
    exchange: str,
    db: Session = Depends(get_db)
):
    """Get real exchange positions (Read-Only)"""
    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == user_id,
        ExchangeCredentials.exchange == exchange.lower(),
        ExchangeCredentials.is_active == True
    ).first()
    
    if not credential:
        raise HTTPException(status_code=404, detail="Exchange credentials not found")
    
    positions = await exchange_service.fetch_positions(
        credential.exchange,
        credential.api_key,
        credential.api_secret,
        credential.passphrase
    )
    
    return {"positions": positions}


@router.get("/real-exchange/orders")
async def get_real_exchange_orders(
    user_id: int,
    exchange: str,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get real exchange open orders (Read-Only)"""
    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == user_id,
        ExchangeCredentials.exchange == exchange.lower(),
        ExchangeCredentials.is_active == True
    ).first()
    
    if not credential:
        raise HTTPException(status_code=404, detail="Exchange credentials not found")
    
    orders = await exchange_service.fetch_open_orders(
        credential.exchange,
        credential.api_key,
        credential.api_secret,
        credential.passphrase,
        symbol
    )
    
    return {"orders": orders}


@router.get("/real-exchange/watch-portfolio")
async def get_real_exchange_watch_portfolio(
    user_id: int,
    exchange: str,
    db: Session = Depends(get_db),
):
    """
    Binance spot izleme portföyü: bakiye, son alış (myTrades), anlık fiyat (ticker), K/Z.
    Yalnızca Binance.
    """
    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == user_id,
        ExchangeCredentials.exchange == exchange.lower(),
        ExchangeCredentials.is_active == True,
    ).first()

    if not credential:
        raise HTTPException(status_code=404, detail="Exchange credentials not found")

    if credential.exchange != "binance":
        raise HTTPException(
            status_code=400,
            detail="İzleme portföyü şu an yalnızca Binance için destekleniyor.",
        )

    data = await exchange_service.fetch_binance_watch_portfolio(
        credential.api_key,
        credential.api_secret,
        credential.passphrase,
    )

    if not data:
        tech = (exchange_service.pop_last_private_error() or "").strip()
        if tech:
            detail_msg = (
                "Binance izleme portföyü alınamadı. Kontrol: API 'Enable Reading', IP kısıtı, "
                "işlem geçmişi izni; çok sayıda coin için işlem biraz sürebilir. Detay: "
                + tech[:1800]
            )
        else:
            detail_msg = (
                "Binance izleme portföyü alınamadı (zaman aşımı veya ağ). Anahtarları ve bağlantıyı kontrol edin."
            )
        raise HTTPException(status_code=504, detail=detail_msg)

    return data


class RealTradeRequest(BaseModel):
    user_id: int
    exchange: str
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    order_type: str = "market"  # 'market' or 'limit'
    price: Optional[float] = None  # Required for limit orders


@router.post("/real-exchange/trade")
async def execute_real_trade(
    trade: RealTradeRequest,
    db: Session = Depends(get_db)
):
    """Execute a real trade on exchange (Real Trading Mode)"""
    credential = db.query(ExchangeCredentials).filter(
        ExchangeCredentials.user_id == trade.user_id,
        ExchangeCredentials.exchange == trade.exchange.lower(),
        ExchangeCredentials.is_active == True,
        ExchangeCredentials.trading_mode == TradingMode.REAL_TRADING
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=404, 
            detail="Exchange credentials not found or not in REAL_TRADING mode"
        )
    
    # Execute trade
    if trade.order_type == "market":
        result = await exchange_service.create_market_order(
            credential.exchange,
            credential.api_key,
            credential.api_secret,
            trade.symbol,
            trade.side,
            trade.amount,
            credential.passphrase
        )
    elif trade.order_type == "limit":
        if not trade.price:
            raise HTTPException(status_code=400, detail="Price is required for limit orders")
        result = await exchange_service.create_limit_order(
            credential.exchange,
            credential.api_key,
            credential.api_secret,
            trade.symbol,
            trade.side,
            trade.amount,
            trade.price,
            credential.passphrase
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid order type")
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to execute trade on exchange")
    
    return {
        "success": True,
        "order": result,
        "message": "Trade executed successfully"
    }


@router.get("/portfolios/{portfolio_id}/rebalancing")
async def get_portfolio_rebalancing(
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Get portfolio rebalancing analysis and recommendations"""
    try:
        analysis = await portfolio_rebalancing_service.analyze_portfolio(db, portfolio_id)
        if not analysis.get("success"):
            raise HTTPException(status_code=404, detail=analysis.get("error", "Portfolio not found"))
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolios/{portfolio_id}/rebalancing/plan")
async def get_rebalancing_plan(
    portfolio_id: int,
    target_allocation: Optional[Dict[str, float]] = Body(None),
    db: Session = Depends(get_db)
):
    """Generate a rebalancing plan for portfolio"""
    try:
        plan = await portfolio_rebalancing_service.get_rebalancing_plan(
            db, portfolio_id, target_allocation
        )
        if not plan.get("success"):
            raise HTTPException(status_code=404, detail=plan.get("error", "Portfolio not found"))
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

