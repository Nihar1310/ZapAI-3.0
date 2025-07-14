from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..database import Base

class Cost(Base):
    __tablename__ = 'costs'

    id = Column(Integer, primary_key=True, index=True)
    search_id = Column(UUID(as_uuid=True), ForeignKey('search_queries.id'), nullable=False)
    firecrawl_cost = Column(Float, default=0.0, nullable=False)
    apollo_cost = Column(Float, default=0.0, nullable=False)
    stripe_fee = Column(Float, default=0.0, nullable=False)

    search_query = relationship("SearchQuery") 