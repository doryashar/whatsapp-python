#!/usr/bin/env python3
"""
Webhook listener script for WhatsApp API events.
Registers a webhook and prints all received events.
"""

import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse


class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8"))
            event_type = payload.get("type", "unknown")
            data = payload.get("data", {})
            timestamp = payload.get("timestamp", 0)

            print(f"\n{'=' * 60}")
            print(f"Event: {event_type}")
            print(f"Timestamp: {timestamp}")
            print(f"Data:")
            print(json.dumps(data, indent=2, default=str))
            print(f"{'=' * 60}\n")
            sys.stdout.flush()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        except Exception as e:
            print(f"Error processing webhook: {e}")
            self.send_response(400)
            self.end_headers()


def register_webhook(api_url: str, api_key: str, webhook_url: str):
    req = urllib.request.Request(
        f"{api_url}/api/webhooks",
        data=json.dumps({"url": webhook_url}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Webhook registered: {result}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Failed to register webhook: {e.code} - {body}")
        return False


def list_webhooks(api_url: str, api_key: str):
    req = urllib.request.Request(
        f"{api_url}/api/webhooks",
        headers={"X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("urls", [])
    except urllib.error.HTTPError as e:
        print(f"Failed to list webhooks: {e.code}")
        return []


def remove_webhook(api_url: str, api_key: str, webhook_url: str):
    req = urllib.request.Request(
        f"{api_url}/api/webhooks?url={urllib.parse.quote(webhook_url, safe='')}",
        headers={"X-API-Key": api_key},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Webhook removed: {result}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Failed to remove webhook: {e.code} - {body}")
        return False


def main():
    parser = argparse.ArgumentParser(description="WhatsApp API webhook listener")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="WhatsApp API URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="API key for authentication",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="Port to listen on (default: 5555)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--external-url",
        help="External URL for webhook (default: http://host:port/webhook)",
    )
    parser.add_argument(
        "--unregister",
        action="store_true",
        help="Unregister webhook and exit",
    )

    args = parser.parse_args()

    webhook_url = args.external_url or f"http://{args.host}:{args.port}/webhook"

    if args.unregister:
        remove_webhook(args.api_url, args.api_key, webhook_url)
        return

    print(f"Starting webhook listener on {args.host}:{args.port}")
    print(f"Webhook URL: {webhook_url}")
    print(f"API URL: {args.api_url}")

    existing = list_webhooks(args.api_url, args.api_key)
    if webhook_url in existing:
        print(f"Webhook already registered")
    else:
        if not register_webhook(args.api_url, args.api_key, webhook_url):
            print("Warning: Failed to register webhook, continuing anyway...")

    print("\nWaiting for events... (Press Ctrl+C to stop)\n")

    server = HTTPServer((args.host, args.port), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
