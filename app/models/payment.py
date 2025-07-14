from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
import enum

class PaymentStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"

class Payment(Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    search_id = Column(Integer, ForeignKey('search_queries.id'), nullable=False)
    stripe_session_id = Column(String, unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.pending)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    search_query = relationship("SearchQuery") 