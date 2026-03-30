from typing import Annotated

from fastapi import Query

from app.core.config import get_settings
from app.schemas.common import PaginationParams


def get_pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = get_settings().default_page_size,
) -> PaginationParams:
    page_size = min(page_size, get_settings().max_page_size)
    return PaginationParams(page=page, page_size=page_size)
