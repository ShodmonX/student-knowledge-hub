import asyncio

from app.bootstrap.seed_service import seed


if __name__ == "__main__":
    asyncio.run(seed())
