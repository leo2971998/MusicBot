import asyncio
import logging

logger = logging.getLogger(__name__)

async def retry_async(coro_func, max_retries=3, base_delay=1.0, *args, **kwargs):
    """Retry an async function with exponential backoff"""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            delay = base_delay * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
    
    logger.error(f"All {max_retries} attempts failed")
    raise last_exception

