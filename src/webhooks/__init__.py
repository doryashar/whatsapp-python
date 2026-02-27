import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional
import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class WebhookSender:
    def __init__(
        self,
        urls: Optional[list[str]] = None,
        secret: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self._urls: list[str] = list(urls or [])
        self._secret = secret or ""
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def add_url(self, url: str) -> None:
        if url not in self._urls:
            self._urls.append(url)

    def remove_url(self, url: str) -> bool:
        try:
            self._urls.remove(url)
            return True
        except ValueError:
            return False

    def _sign_payload(self, payload: str) -> str:
        if not self._secret:
            return ""
        signature = hmac.new(
            self._secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"

    async def _send_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: str,
        signature: str,
    ) -> bool:
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
        }

        for attempt in range(self._max_retries):
            try:
                response = await client.post(
                    url,
                    content=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                if 200 <= response.status_code < 300:
                    return True
                logger.warning(
                    f"Webhook to {url} returned {response.status_code}, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )
            except httpx.TimeoutException:
                logger.warning(
                    f"Webhook to {url} timed out, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )
            except Exception as e:
                logger.warning(
                    f"Webhook to {url} failed: {e}, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )

            if attempt < self._max_retries - 1:
                backoff = (2**attempt) * 0.5
                await asyncio.sleep(backoff)

        return False

    async def send(self, event_type: str, data: dict[str, Any]) -> dict[str, bool]:
        if not self._urls:
            return {}

        payload = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": int(time.time()),
            },
            separators=(",", ":"),
        )
        signature = self._sign_payload(payload)

        async with httpx.AsyncClient() as client:
            results = {}
            tasks = [
                self._send_with_retry(client, url, payload, signature)
                for url in self._urls
            ]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)

            for url, outcome in zip(self._urls, outcomes):
                if isinstance(outcome, Exception):
                    logger.error(f"Webhook to {url} raised exception: {outcome}")
                    results[url] = False
                else:
                    results[url] = outcome

            return results

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


webhook_sender = WebhookSender(
    urls=settings.webhook_urls,
    secret=settings.webhook_secret,
    timeout=settings.webhook_timeout,
    max_retries=settings.webhook_retries,
)
