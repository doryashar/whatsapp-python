import pytest
from unittest.mock import Mock, AsyncMock


class TestEditedMessageFormatting:
    @pytest.fixture
    def config(self):
        from src.chatwoot import ChatwootConfig

        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    def test_edited_text_appends_old_content(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Hello world",
                "is_edited": True,
                "edited_text": "Goodbye world",
            },
            is_edited=True,
        )

        assert "Hello world" in result
        assert "Goodbye world" in result
        assert "*Edited to:*" in result
        assert result.index("Hello world") < result.index("*Edited to:*")
        assert result.index("*Edited to:*") < result.index("Goodbye world")

    def test_not_edited_no_change(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Hello world",
                "is_edited": False,
            },
            is_edited=False,
        )

        assert result == "Hello world"
        assert "Edited" not in result

    def test_edited_same_content_no_append(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Identical",
                "is_edited": True,
                "edited_text": "Identical",
            },
            is_edited=True,
        )

        assert result == "Identical"
        assert "Edited to" not in result

    def test_edited_no_edited_text_field(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Original",
                "is_edited": True,
            },
            is_edited=True,
        )

        assert result == "Original"
        assert "Edited" not in result

    def test_edited_empty_content(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "",
                "is_edited": True,
                "edited_text": "New content",
            },
            is_edited=True,
        )

        assert result is None or "Edited" not in (result or "")

    def test_edited_with_multiline(self, config, mock_tenant, mock_bridge):
        from src.chatwoot import ChatwootIntegration

        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Line 1\nLine 2",
                "is_edited": True,
                "edited_text": "Updated",
            },
            is_edited=True,
        )

        assert "Line 1\nLine 2" in result
        assert "Updated" in result
        assert "*Edited to:*" in result
