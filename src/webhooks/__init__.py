import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING
import httpx

from ..config import settings
from ..telemetry import get_logger

if TYPE_CHECKING:
    from ..store.database import Database

logger = get_logger("whatsapp.webhooks")


@dataclass
class WebhookResult:
    url: str
    success: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    attempt_number: int = 1
    latency_ms: int = 0


class WebhookSender:
    def __init__(
        self,
        urls: Optional[list[str]] = None,
        secret: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        tenant_hash: Optional[str] = None,
        db: Optional["Database"] = None,
    ):
        self._urls: list[str] = list(urls or [])
        self._secret = secret or ""
        self._timeout = timeout
        self._max_retries = max_retries
        self._tenant_hash = tenant_hash
        self._db = db
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

    async def _save_attempt(
        self,
        url: str,
        event_type: str,
        result: WebhookResult,
        payload_preview: Optional[str] = None,
    ) -> None:
        if self._db and self._tenant_hash:
            try:
                await self._db.save_webhook_attempt(
                    tenant_hash=self._tenant_hash,
                    url=url,
                    event_type=event_type,
                    success=result.success,
                    status_code=result.status_code,
                    error_message=result.error_message,
                    attempt_number=result.attempt_number,
                    latency_ms=result.latency_ms,
                    payload_preview=payload_preview,
                )
            except Exception as e:
                logger.error(f"Failed to save webhook attempt: {e}")

    async def _send_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: str,
        signature: str,
        event_type: str,
    ) -> WebhookResult:
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
        }

        payload_preview = payload[:500] if len(payload) > 500 else payload
        start_time = time.time()
        last_error: Optional[str] = None
        last_status_code: Optional[int] = None
        successful_attempt = 0

        for attempt in range(self._max_retries):
            attempt_start = time.time()
            try:
                response = await client.post(
                    url,
                    content=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                last_status_code = response.status_code

                if 200 <= response.status_code < 300:
                    latency = int((time.time() - start_time) * 1000)
                    result = WebhookResult(
                        url=url,
                        success=True,
                        status_code=response.status_code,
                        attempt_number=attempt + 1,
                        latency_ms=latency,
                    )
                    await self._save_attempt(url, event_type, result, payload_preview)
                    return result
                else:
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(
                        f"Webhook to {url} returned {response.status_code}, "
                        f"attempt {attempt + 1}/{self._max_retries}"
                    )
            except httpx.TimeoutException:
                last_error = "Timeout"
                logger.warning(
                    f"Webhook to {url} timed out, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )
            except httpx.ConnectError as e:
                last_error = f"Connection failed: {str(e)[:100]}"
                logger.warning(
                    f"Webhook to {url} connection failed, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )
            except Exception as e:
                last_error = str(e)[:200]
                logger.warning(
                    f"Webhook to {url} failed: {e}, "
                    f"attempt {attempt + 1}/{self._max_retries}"
                )

            if attempt < self._max_retries - 1:
                backoff = (2**attempt) * 0.5
                await asyncio.sleep(backoff)

        latency = int((time.time() - start_time) * 1000)
        result = WebhookResult(
            url=url,
            success=False,
            status_code=last_status_code,
            error_message=last_error,
            attempt_number=self._max_retries,
            latency_ms=latency,
        )
        await self._save_attempt(url, event_type, result, payload_preview)
        return result

    async def send(
        self, event_type: str, data: dict[str, Any]
    ) -> dict[str, WebhookResult]:
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
            tasks = [
                self._send_with_retry(client, url, payload, signature, event_type)
                for url in self._urls
            ]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)

            results = {}
            for url, outcome in zip(self._urls, outcomes):
                if isinstance(outcome, Exception):
                    logger.error(f"Webhook to {url} raised exception: {outcome}")
                    results[url] = WebhookResult(
                        url=url,
                        success=False,
                        error_message=str(outcome),
                    )
                else:
                    results[url] = outcome

            return results

    async def send_simple(
        self, event_type: str, data: dict[str, Any]
    ) -> dict[str, bool]:
        results = await self.send(event_type, data)
        return {url: r.success for url, r in results.items()}

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
