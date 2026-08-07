import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.database import Base


class ConvState(str, enum.Enum):
    idle = "idle"
    welcome = "welcome"
    main_menu = "main_menu"
    category = "category"
    item_detail = "item_detail"
    cart = "cart"
    confirm = "confirm"
    payment = "payment"
    address = "address"
    placed = "placed"
    rating = "rating"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    is_vip = Column(Boolean, default=False, nullable=False)
    conv_state = Column(String, default=ConvState.idle.value, nullable=False)
    conv_data = Column(JSON, default=dict, nullable=False)
    total_orders = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    orders = relationship("Order", back_populates="customer")
