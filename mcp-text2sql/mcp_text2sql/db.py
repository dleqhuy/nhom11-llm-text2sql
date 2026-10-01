from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True, pool_pre_ping=True)

@contextmanager
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as conn:
        yield conn
