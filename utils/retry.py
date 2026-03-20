"""tenacity 기반 재시도 데코레이터"""

import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# 일반 API 호출용 (3회 재시도, 2~60초 대기)
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# Rate Limit용 (5회 재시도, 5~120초 대기)
rate_limit_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=120),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
