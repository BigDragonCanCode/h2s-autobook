from __future__ import annotations

import argparse
import logging
import os

import curl_cffi.requests as req
from dotenv import load_dotenv

from booker import cancel_order_by_id, fetch_customer_orders, login
from config import ENV_PATH, get_impersonate, get_proxy_url

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cancel one Holland2Stay order by id")
    parser.add_argument("order_id", help="Magento order id/uid used by cancelOrder")
    args = parser.parse_args()

    load_dotenv(dotenv_path=ENV_PATH, override=True)
    _setup_logging()

    email = os.environ.get("H2S_EMAIL", "").strip()
    password = os.environ.get("H2S_PASSWORD", "")
    if not email or not password:
        print("H2S_EMAIL or H2S_PASSWORD missing in .env")
        return 1

    proxy = get_proxy_url()
    proxies = {"https": proxy, "http": proxy} if proxy else {}
    logger.info("starting single-order cancel for order_id=%s", args.order_id)
    logger.info("proxy configured=%s", "yes" if proxy else "no")
    session = req.Session(impersonate=get_impersonate(), proxies=proxies)

    try:
        logger.info("logging in as %s", email)
        token = login(session, email, password)
        orders = fetch_customer_orders(session, token)
        logger.info("current customer orders: %r", orders)
        logger.info("login succeeded; submitting cancelOrder")
        cancel_order_by_id(session, token, args.order_id)
        logger.info("cancelOrder succeeded for order_id=%s", args.order_id)
        print(f"Cancelled order: {args.order_id}")
        return 0
    except Exception:
        logger.exception("cancelOrder failed for order_id=%s", args.order_id)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
