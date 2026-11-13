"""NinjaTrader 8 integration via ATI (Automated Trading Interface)"""
import socket
import time
import threading
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from enum import Enum
from queue import Queue
from loguru import logger


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOPLIMIT"


class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELLSHORT"
    BUY_TO_COVER = "BUYTOCOVER"


class OrderState(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    WORKING = "working"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PARTIAL = "partial"


@dataclass
class NTOrder:
    """NinjaTrader order representation"""
    order_id: str
    instrument: str
    action: OrderAction
    quantity: int
    order_type: OrderType
    price: Optional[float] = None
    stop_price: Optional[float] = None
    state: OrderState = OrderState.PENDING
    filled_quantity: int = 0
    fill_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    oco_id: Optional[str] = None
    
    def to_ati_command(self) -> str:
        """Convert to NinjaTrader ATI command format"""
        cmd_parts = [
            "PLACE",
            self.instrument,
            self.action.value,
            str(self.quantity),
            self.order_type.value
        ]
        
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            cmd_parts.append(str(self.price))
            
        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            cmd_parts.append(str(self.stop_price))
            
        if self.oco_id:
            cmd_parts.append(f"OCO={self.oco_id}")
            
        return ";".join(cmd_parts)


@dataclass
class Position:
    """Position information"""
    instrument: str
    quantity: int
    avg_price: float
    unrealized_pnl: float
    realized_pnl: float
    market_position: str  # "Long", "Short", "Flat"


class NinjaTraderConnection:
    """
    NinjaTrader 8 connection via ATI (Automated Trading Interface).
    
    ATI allows external programs to send commands to NinjaTrader.
    Communication is typically via file-based commands or TCP socket.
    
    This implementation supports both methods:
    1. File-based: Write commands to incoming folder, read responses from outgoing
    2. Socket-based: TCP connection to NinjaTrader's ATI server
    """
    
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 36973  # Default NinjaTrader ATI port
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        account: str = "Sim101",
        use_socket: bool = True,
        ati_folder: Optional[str] = None,
        reconnect_attempts: int = 3,
        reconnect_delay: float = 5.0
    ):
        self.host = host
        self.port = port
        self.account = account
        self.use_socket = use_socket
        self.ati_folder = ati_folder
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        
        # Connection state
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
        
        # Order tracking
        self._orders: Dict[str, NTOrder] = {}
        self._order_counter = 0
        
        # Callbacks
        self._on_fill: Optional[Callable[[NTOrder], None]] = None
        self._on_position_update: Optional[Callable[[Position], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        
        # Response queue for async operations
        self._response_queue: Queue = Queue()
        
        # Reader thread
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        
    def connect(self) -> bool:
        """Establish connection to NinjaTrader"""
        if self._connected:
            logger.warning("Already connected to NinjaTrader")
            return True
            
        for attempt in range(self.reconnect_attempts):
            try:
                if self.use_socket:
                    return self._connect_socket()
                else:
                    return self._connect_file_based()
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.reconnect_attempts - 1:
                    time.sleep(self.reconnect_delay)
                    
        logger.error("Failed to connect to NinjaTrader after all attempts")
        return False
    
    def _connect_socket(self) -> bool:
        """Connect via TCP socket"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(10.0)
            self._socket.connect((self.host, self.port))
            self._connected = True
            
            # Start reader thread
            self._running = True
            self._reader_thread = threading.Thread(target=self._socket_reader, daemon=True)
            self._reader_thread.start()
            
            logger.info(f"Connected to NinjaTrader at {self.host}:{self.port}")
            return True
            
        except socket.error as e:
            logger.error(f"Socket connection failed: {e}")
            return False
    
    def _connect_file_based(self) -> bool:
        """Set up file-based ATI connection"""
        if not self.ati_folder:
            logger.error("ATI folder not specified for file-based connection")
            return False
            
        # Verify ATI folders exist
        import os
        incoming = os.path.join(self.ati_folder, "incoming")
        outgoing = os.path.join(self.ati_folder, "outgoing")
        
        if not os.path.exists(incoming) or not os.path.exists(outgoing):
            logger.error("ATI folders not found")
            return False
            
        self._connected = True
        logger.info(f"File-based ATI connection ready at {self.ati_folder}")
        return True
    
    def disconnect(self):
        """Disconnect from NinjaTrader"""
        self._running = False
        
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
            
        self._connected = False
        logger.info("Disconnected from NinjaTrader")
        
    def _socket_reader(self):
        """Background thread to read socket responses"""
        buffer = ""
        while self._running:
            try:
                if self._socket:
                    self._socket.settimeout(1.0)
                    data = self._socket.recv(4096)
                    if data:
                        buffer += data.decode('utf-8')
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            self._process_response(line.strip())
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Socket reader error: {e}")
                break
                
    def _process_response(self, response: str):
        """Process response from NinjaTrader"""
        logger.debug(f"NT Response: {response}")
        
        try:
            # Parse response (format varies by command)
            if response.startswith("ORDER"):
                self._handle_order_update(response)
            elif response.startswith("POSITION"):
                self._handle_position_update(response)
            elif response.startswith("ERROR"):
                self._handle_error(response)
            else:
                self._response_queue.put(response)
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            
    def _handle_order_update(self, response: str):
        """Handle order status update"""
        parts = response.split(";")
        if len(parts) >= 3:
            order_id = parts[1]
            status = parts[2]
            
            if order_id in self._orders:
                order = self._orders[order_id]
                
                if status == "FILLED":
                    order.state = OrderState.FILLED
                    order.filled_quantity = order.quantity
                    if len(parts) >= 4:
                        order.fill_price = float(parts[3])
                    if self._on_fill:
                        self._on_fill(order)
                        
                elif status == "CANCELLED":
                    order.state = OrderState.CANCELLED
                    
                elif status == "REJECTED":
                    order.state = OrderState.REJECTED
                    
                elif status == "ACCEPTED":
                    order.state = OrderState.ACCEPTED
                    
                elif status == "WORKING":
                    order.state = OrderState.WORKING
                    
    def _handle_position_update(self, response: str):
        """Handle position update"""
        parts = response.split(";")
        if len(parts) >= 6:
            position = Position(
                instrument=parts[1],
                quantity=int(parts[2]),
                avg_price=float(parts[3]),
                unrealized_pnl=float(parts[4]),
                realized_pnl=float(parts[5]),
                market_position=parts[6] if len(parts) > 6 else "Flat"
            )
            if self._on_position_update:
                self._on_position_update(position)
                
    def _handle_error(self, response: str):
        """Handle error response"""
        error_msg = response.replace("ERROR;", "")
        logger.error(f"NinjaTrader error: {error_msg}")
        if self._on_error:
            self._on_error(error_msg)
            
    def _send_command(self, command: str) -> bool:
        """Send command to NinjaTrader"""
        if not self._connected:
            logger.error("Not connected to NinjaTrader")
            return False
            
        with self._lock:
            try:
                if self.use_socket and self._socket:
                    self._socket.sendall((command + "\n").encode('utf-8'))
                else:
                    self._write_command_file(command)
                logger.debug(f"Sent command: {command}")
                return True
            except Exception as e:
                logger.error(f"Failed to send command: {e}")
                return False
                
    def _write_command_file(self, command: str):
        """Write command to ATI incoming folder"""
        import os
        filename = f"cmd_{int(time.time() * 1000)}.txt"
        filepath = os.path.join(self.ati_folder, "incoming", filename)
        with open(filepath, 'w') as f:
            f.write(command)
            
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        self._order_counter += 1
        return f"PY_{int(time.time())}_{self._order_counter}"
        
    def place_market_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int
    ) -> Optional[NTOrder]:
        """Place a market order"""
        order_id = self._generate_order_id()
        
        order = NTOrder(
            order_id=order_id,
            instrument=instrument,
            action=action,
            quantity=quantity,
            order_type=OrderType.MARKET
        )
        
        command = f"PLACE;{self.account};{instrument};{action.value};{quantity};MARKET;;{order_id}"
        
        if self._send_command(command):
            self._orders[order_id] = order
            return order
        return None
        
    def place_limit_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        limit_price: float
    ) -> Optional[NTOrder]:
        """Place a limit order"""
        order_id = self._generate_order_id()
        
        order = NTOrder(
            order_id=order_id,
            instrument=instrument,
            action=action,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )
        
        command = f"PLACE;{self.account};{instrument};{action.value};{quantity};LIMIT;{limit_price};{order_id}"
        
        if self._send_command(command):
            self._orders[order_id] = order
            return order
        return None
        
    def place_stop_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        stop_price: float
    ) -> Optional[NTOrder]:
        """Place a stop order"""
        order_id = self._generate_order_id()
        
        order = NTOrder(
            order_id=order_id,
            instrument=instrument,
            action=action,
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=stop_price
        )
        
        command = f"PLACE;{self.account};{instrument};{action.value};{quantity};STOPMARKET;{stop_price};{order_id}"
        
        if self._send_command(command):
            self._orders[order_id] = order
            return order
        return None
        
    def place_bracket_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        stop_loss: float,
        take_profit: float,
        entry_type: OrderType = OrderType.MARKET,
        entry_price: Optional[float] = None
    ) -> Dict[str, NTOrder]:
        """Place a bracket order (entry + stop loss + take profit)"""
        oco_id = self._generate_order_id()
        orders = {}
        
        # Entry order
        entry_order = NTOrder(
            order_id=self._generate_order_id(),
            instrument=instrument,
            action=action,
            quantity=quantity,
            order_type=entry_type,
            price=entry_price if entry_type != OrderType.MARKET else None
        )
        
        # Determine exit action
        exit_action = OrderAction.SELL if action in [OrderAction.BUY, OrderAction.BUY_TO_COVER] else OrderAction.BUY_TO_COVER
        
        # Stop loss order
        sl_order = NTOrder(
            order_id=self._generate_order_id(),
            instrument=instrument,
            action=exit_action,
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=stop_loss,
            oco_id=oco_id
        )
        
        # Take profit order
        tp_order = NTOrder(
            order_id=self._generate_order_id(),
            instrument=instrument,
            action=exit_action,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=take_profit,
            oco_id=oco_id
        )
        
        # Send entry first
        if entry_type == OrderType.MARKET:
            cmd = f"PLACE;{self.account};{instrument};{action.value};{quantity};MARKET;;{entry_order.order_id}"
        else:
            cmd = f"PLACE;{self.account};{instrument};{action.value};{quantity};LIMIT;{entry_price};{entry_order.order_id}"
            
        if self._send_command(cmd):
            self._orders[entry_order.order_id] = entry_order
            orders["entry"] = entry_order
            
        # Send OCO bracket
        sl_cmd = f"PLACE;{self.account};{instrument};{exit_action.value};{quantity};STOPMARKET;{stop_loss};{sl_order.order_id};OCO={oco_id}"
        tp_cmd = f"PLACE;{self.account};{instrument};{exit_action.value};{quantity};LIMIT;{take_profit};{tp_order.order_id};OCO={oco_id}"
        
        if self._send_command(sl_cmd):
            self._orders[sl_order.order_id] = sl_order
            orders["stop_loss"] = sl_order
            
        if self._send_command(tp_cmd):
            self._orders[tp_order.order_id] = tp_order
            orders["take_profit"] = tp_order
            
        return orders
        
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        command = f"CANCEL;{self.account};;{order_id}"
        return self._send_command(command)
        
    def cancel_all_orders(self, instrument: Optional[str] = None) -> bool:
        """Cancel all orders (optionally for specific instrument)"""
        if instrument:
            command = f"CANCELALLORDERS;{self.account};{instrument}"
        else:
            command = f"CANCELALLORDERS;{self.account}"
        return self._send_command(command)
        
    def flatten_position(self, instrument: str) -> bool:
        """Close all positions for instrument"""
        command = f"FLATTENEVERYTHING;{self.account}"
        return self._send_command(command)
        
    def get_position(self, instrument: str) -> Optional[Position]:
        """Request current position for instrument"""
        command = f"REQPOSITION;{self.account};{instrument}"
        if self._send_command(command):
            try:
                response = self._response_queue.get(timeout=5.0)
                if response.startswith("POSITION"):
                    parts = response.split(";")
                    return Position(
                        instrument=parts[1],
                        quantity=int(parts[2]),
                        avg_price=float(parts[3]),
                        unrealized_pnl=float(parts[4]),
                        realized_pnl=float(parts[5]),
                        market_position=parts[6] if len(parts) > 6 else "Flat"
                    )
            except Exception:
                pass
        return None
        
    def subscribe_to_fills(self, callback: Callable[[NTOrder], None]):
        """Subscribe to fill notifications"""
        self._on_fill = callback
        
    def subscribe_to_positions(self, callback: Callable[[Position], None]):
        """Subscribe to position updates"""
        self._on_position_update = callback
        
    def subscribe_to_errors(self, callback: Callable[[str], None]):
        """Subscribe to error notifications"""
        self._on_error = callback
        
    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
        
    def get_orders(self) -> Dict[str, NTOrder]:
        """Get all tracked orders"""
        return self._orders.copy()


class OrderManager:
    """
    Higher-level order management for the trading bot.
    
    Wraps NinjaTraderConnection with additional features:
    - Order tracking and reconciliation
    - Retry logic
    - Position synchronization
    """
    
    def __init__(self, connection: NinjaTraderConnection):
        self.conn = connection
        self._position: int = 0
        self._pending_orders: Dict[str, NTOrder] = {}
        
        # Subscribe to updates
        self.conn.subscribe_to_fills(self._on_fill)
        self.conn.subscribe_to_positions(self._on_position)
        
    def _on_fill(self, order: NTOrder):
        """Handle order fill"""
        logger.info(f"Order filled: {order.order_id} @ {order.fill_price}")
        
        # Update position
        if order.action in [OrderAction.BUY, OrderAction.BUY_TO_COVER]:
            self._position += order.filled_quantity
        else:
            self._position -= order.filled_quantity
            
        # Remove from pending
        self._pending_orders.pop(order.order_id, None)
        
    def _on_position(self, position: Position):
        """Handle position update"""
        self._position = position.quantity
        logger.info(f"Position update: {position.instrument} = {position.quantity}")
        
    def enter_long(
        self,
        instrument: str,
        quantity: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Enter long position with optional bracket orders"""
        if stop_loss and take_profit:
            orders = self.conn.place_bracket_order(
                instrument=instrument,
                action=OrderAction.BUY,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            return "entry" in orders
        else:
            order = self.conn.place_market_order(instrument, OrderAction.BUY, quantity)
            return order is not None
            
    def enter_short(
        self,
        instrument: str,
        quantity: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Enter short position with optional bracket orders"""
        if stop_loss and take_profit:
            orders = self.conn.place_bracket_order(
                instrument=instrument,
                action=OrderAction.SELL_SHORT,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            return "entry" in orders
        else:
            order = self.conn.place_market_order(instrument, OrderAction.SELL_SHORT, quantity)
            return order is not None
            
    def close_position(self, instrument: str) -> bool:
        """Close all positions"""
        return self.conn.flatten_position(instrument)
        
    def get_position(self) -> int:
        """Get current position"""
        return self._position
