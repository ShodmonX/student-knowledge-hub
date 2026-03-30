import asyncio

from app.services.seed_service import seed


if __name__ == "__main__":
    asyncio.run(seed())
