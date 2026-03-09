#!/usr/bin/env python3
"""
Manual test script for OpenCode WhatsApp integration.

This script allows testing the integration without needing WhatsApp connected.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.sample_integration.session_manager import SessionManager


async def test_session_manager():
    """Test session manager functionality."""
    print("=" * 60)
    print("Testing Session Manager")
    print("=" * 60)

    manager = SessionManager("./data/test_sessions.db")
    await manager.init_db()

    print("\n1. Testing create_session...")
    await manager.create_session("test_user@s.whatsapp.net", "test_session_123")
    print("   ✓ Session created")

    print("\n2. Testing get_session...")
    session_id = await manager.get_session("test_user@s.whatsapp.net")
    print(f"   ✓ Retrieved session: {session_id}")

    print("\n3. Testing list_sessions...")
    sessions = await manager.list_sessions()
    print(f"   ✓ Found {len(sessions)} sessions")
    for session in sessions:
        print(f"      - {session['chat_jid']}: {session['opencode_session_id']}")

    print("\n4. Testing delete_session...")
    deleted = await manager.delete_session("test_user@s.whatsapp.net")
    print(f"   ✓ Deleted: {deleted}")

    await manager.close()
    print("\n✓ Session Manager tests completed\n")


async def test_webhook_handler_health():
    """Test webhook handler health endpoint."""
    print("=" * 60)
    print("Testing Webhook Handler")
    print("=" * 60)

    import httpx

    print("\n1. Testing health endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:5556/health", timeout=5.0)
            if response.status_code == 200:
                print(f"   ✓ Health check passed: {response.json()}")
            else:
                print(f"   ✗ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"   ✗ Could not connect to webhook handler: {e}")
        print("   Make sure to start the handler first:")
        print("   python scripts/opencode_webhook_handler.py")

    print()


async def test_opencode_integration():
    """Test OpenCode CLI integration."""
    print("=" * 60)
    print("Testing OpenCode Integration")
    print("=" * 60)

    print("\n1. Testing opencode run command...")

    from scripts.sample_integration.opencode_webhook_handler import run_opencode

    try:
        result = await run_opencode(
            message="Say 'Hello, this is a test'", prompt_file="PROMPT.md", files=None
        )

        print(f"   ✓ OpenCode response received")
        print(f"   Session ID: {result.get('session_id')}")
        print(f"   Response text (first 100 chars): {result.get('text', '')[:100]}...")
    except Exception as e:
        print(f"   ✗ OpenCode integration failed: {e}")
        print("   Make sure OpenCode is installed: opencode --version")

    print()


async def test_full_message_flow():
    """Test complete message processing flow."""
    print("=" * 60)
    print("Testing Full Message Flow")
    print("=" * 60)

    from unittest.mock import AsyncMock, patch
    from scripts.sample_integration.opencode_webhook_handler import (
        process_message,
    )
    from scripts.sample_integration.session_manager import SessionManager
    import scripts.sample_integration.opencode_webhook_handler as handler_module

    print("\nInitializing session manager...")
    test_session_manager = SessionManager("./data/test_sessions_flow.db")
    await test_session_manager.init_db()

    handler_module.session_manager = test_session_manager

    print("\n1. Simulating incoming message...")
    message_data = {
        "chat_jid": "+1234567890@s.whatsapp.net",
        "text": "Hello, this is a test message",
        "type": "text",
        "from_me": False,
        "id": "test_msg_123",
    }

    print(f"   From: {message_data['chat_jid']}")
    print(f"   Text: {message_data['text']}")

    print("\n2. Processing message (this may take a moment)...")
    try:
        with patch(
            "scripts.sample_integration.opencode_webhook_handler.run_opencode",
            new_callable=AsyncMock,
        ) as mock_run:
            with patch(
                "scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message",
                new_callable=AsyncMock,
            ):
                mock_run.return_value = {
                    "session_id": "test_session_123",
                    "text": "Test response",
                }
                await process_message(message_data)
                print("   ✓ Message processed")
    except Exception as e:
        print(f"   ✗ Message processing failed: {e}")

    print("\n3. Checking session was created...")
    session_id = await test_session_manager.get_session(message_data["chat_jid"])
    if session_id:
        print(f"   ✓ Session created: {session_id}")
    else:
        print("   ✗ Session not created")

    print("\n4. Simulating follow-up message...")
    follow_up = {
        "chat_jid": message_data["chat_jid"],
        "text": "Can you tell me more?",
        "type": "text",
        "from_me": False,
    }

    try:
        with patch(
            "scripts.sample_integration.opencode_webhook_handler.run_opencode",
            new_callable=AsyncMock,
        ) as mock_run:
            with patch(
                "scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message",
                new_callable=AsyncMock,
            ):
                mock_run.return_value = {
                    "session_id": session_id,
                    "text": "Follow-up response",
                }
                await process_message(follow_up)
                print("   ✓ Follow-up processed")
    except Exception as e:
        print(f"   ✗ Follow-up failed: {e}")
    finally:
        await test_session_manager.close()
        handler_module.session_manager = None

    print("\n✓ Full flow test completed\n")


def print_menu():
    """Print test menu."""
    print("\n" + "=" * 60)
    print("OpenCode WhatsApp Integration - Test Suite")
    print("=" * 60)
    print("\nAvailable tests:")
    print("  1. Session Manager")
    print("  2. Webhook Handler Health")
    print("  3. OpenCode Integration")
    print("  4. Full Message Flow")
    print("  5. Run All Tests")
    print("  0. Exit")
    print()


async def main():
    """Main test runner."""
    while True:
        print_menu()
        choice = input("Select test (0-5): ").strip()

        if choice == "1":
            await test_session_manager()
        elif choice == "2":
            await test_webhook_handler_health()
        elif choice == "3":
            await test_opencode_integration()
        elif choice == "4":
            await test_full_message_flow()
        elif choice == "5":
            await test_session_manager()
            await test_webhook_handler_health()
            await test_opencode_integration()
            await test_full_message_flow()
        elif choice == "0":
            print("\nGoodbye!\n")
            break
        else:
            print("\nInvalid choice. Please try again.\n")

        if choice != "0":
            input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted. Goodbye!\n")
