"""Generic pagination utilities.

Usage in a router:

    @router.get("", response_model=Page[CustomerOut])
    def list_customers(
        params: PageParams = Depends(),
        db: Session = Depends(get_db),
    ):
        q = db.query(Customer)
        return paginate(q, params)
"""
from typing import Generic, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy.orm import Query as SAQuery

T = TypeVar("T")


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=200),
    ):
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


def paginate(query: SAQuery, params: PageParams) -> dict:
    """Returns a dict matching `Page[T]` after FastAPI serialization."""
    total = query.order_by(None).count()
    rows: Sequence = query.offset(params.offset).limit(params.size).all()
    pages = (total + params.size - 1) // params.size if params.size else 1
    return {
        "items": rows,
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": pages,
    }
