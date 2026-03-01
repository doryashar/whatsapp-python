#!/usr/bin/env python3
"""
WebSocket client script for WhatsApp API events.
Connects to the WebSocket endpoint and prints all received events.
"""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime

try:
    import websockets
except ImportError:
    print("Error: websockets library required. Install with: pip install websockets")
    sys.exit(1)


async def websocket_client(api_url: str, api_key: str):
    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/events?api_key={api_key}"

    print(f"Connecting to WebSocket: {ws_url[:50]}...")
    print("Waiting for events... (Press Ctrl+C to stop)\n")

    shutdown_event = asyncio.Event()

    def signal_handler():
        print("\n\nShutting down...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"Connected at {datetime.now().isoformat()}\n")

            async def receive_events():
                async for message in websocket:
                    try:
                        event = json.loads(message)
                        event_type = event.get("type", "unknown")
                        data = event.get("data", {})
                        timestamp = datetime.now().isoformat()

                        print(f"{'=' * 60}")
                        print(f"[{timestamp}] Event: {event_type}")
                        print(f"Data:")
                        print(json.dumps(data, indent=2, default=str)[:1000])
                        if len(json.dumps(data)) > 1000:
                            print("... (truncated)")
                        print(f"{'=' * 60}\n")
                        sys.stdout.flush()
                    except json.JSONDecodeError as e:
                        print(f"Invalid JSON received: {e}")

            async def send_ping():
                while not shutdown_event.is_set():
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=30)
                    except asyncio.TimeoutError:
                        await websocket.send(json.dumps({"type": "ping"}))

            await asyncio.gather(
                receive_events(),
                send_ping(),
                return_exceptions=True,
            )

    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code == 401:
            print("Error: Invalid API key")
        else:
            print(f"Error: HTTP {e.status_code}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e.reason}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        loop.remove_signal_handler(signal.SIGINT)
        loop.remove_signal_handler(signal.SIGTERM)


async def send_test_message(api_url: str, api_key: str, to: str, text: str):
    import urllib.request

    data = json.dumps({"to": to, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/api/send",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Test message sent: {result}")
    except Exception as e:
        print(f"Failed to send test message: {e}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp API WebSocket listener")
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
        "--test-message",
        action="store_true",
        help="Send a test message after connecting",
    )
    parser.add_argument(
        "--test-to",
        default="972548826569",
        help="Phone number to send test message to (default: 972548826569)",
    )

    args = parser.parse_args()

    if args.test_message:
        print("Sending test message to trigger events...")
        asyncio.run(
            send_test_message(
                args.api_url, args.api_key, args.test_to, "WebSocket test!"
            )
        )
        print()

    asyncio.run(websocket_client(args.api_url, args.api_key))


if __name__ == "__main__":
    main()
