import pytest
from pydantic import ValidationError


class TestSendStatusValidation:
    def test_valid_status_with_jid_list(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="text",
            content="Hello world",
            status_jid_list=["1234567890@s.whatsapp.net"],
        )
        assert req.type == "text"
        assert req.all_contacts is False

    def test_valid_status_with_all_contacts(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="image",
            content="https://example.com/image.jpg",
            all_contacts=True,
        )
        assert req.type == "image"
        assert req.all_contacts is True
        assert req.status_jid_list is None

    def test_invalid_both_recipients(self):
        from src.models.group import SendStatusRequest

        with pytest.raises(ValidationError) as exc_info:
            SendStatusRequest(
                type="text",
                content="Hello",
                status_jid_list=["1234567890@s.whatsapp.net"],
                all_contacts=True,
            )
        assert "Cannot specify both" in str(exc_info.value)

    def test_invalid_no_recipients(self):
        from src.models.group import SendStatusRequest

        with pytest.raises(ValidationError) as exc_info:
            SendStatusRequest(
                type="text",
                content="Hello",
            )
        assert "Must specify either" in str(exc_info.value)

    def test_invalid_type(self):
        from src.models.group import SendStatusRequest

        with pytest.raises(ValidationError) as exc_info:
            SendStatusRequest(
                type="audio",
                content="data",
                status_jid_list=["1234567890@s.whatsapp.net"],
            )
        assert "type" in str(exc_info.value).lower()

    def test_valid_video_status(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="video",
            content="https://example.com/video.mp4",
            status_jid_list=["1234567890@s.whatsapp.net"],
        )
        assert req.type == "video"

    def test_empty_jid_list_treated_as_no_recipients(self):
        from src.models.group import SendStatusRequest

        with pytest.raises(ValidationError):
            SendStatusRequest(
                type="text",
                content="Hello",
                status_jid_list=[],
            )

    def test_optional_fields_defaults(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="text",
            content="Hello",
            status_jid_list=["1234567890@s.whatsapp.net"],
        )
        assert req.caption is None
        assert req.background_color == "#25D366"
        assert req.font == 1

    def test_custom_optional_fields(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="text",
            content="Hello",
            status_jid_list=["1234567890@s.whatsapp.net"],
            caption="My caption",
            background_color="#FF0000",
            font=2,
        )
        assert req.caption == "My caption"
        assert req.background_color == "#FF0000"
        assert req.font == 2
