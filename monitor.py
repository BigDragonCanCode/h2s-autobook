from __future__ import annotations

import logging
import random
import time

from dotenv import load_dotenv

from config import ENV_PATH, load_config
from run import run_once, setup_logging


def _sleep_interval() -> int:
    cfg = load_config()
    base_interval = max(5, cfg.check_interval)
    jitter_ratio = max(0.0, min(0.5, cfg.jitter_ratio))
    delta = int(round(base_interval * jitter_ratio))
    if delta <= 0:
        return base_interval
    return max(5, random.randint(base_interval - delta, base_interval + delta))


def main() -> int:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("monitor started; press Ctrl+C to stop")

    while True:
        try:
            load_dotenv(dotenv_path=ENV_PATH, override=True)
            cfg = load_config()
            logger.info("starting monitor cycle (interval=%ss)", cfg.check_interval)
            exit_code = run_once()
            if exit_code != 0:
                logger.warning("monitor cycle finished with exit code %s; continuing", exit_code)

            sleep_seconds = _sleep_interval()
            logger.info("cycle complete; sleeping %s seconds", sleep_seconds)
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logger.info("monitor stopped by user")
            return 0
        except Exception:
            logger.exception("monitor cycle crashed; retrying in 10 seconds")
            time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
