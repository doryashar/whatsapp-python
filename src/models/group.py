from typing import Optional, Literal
from pydantic import BaseModel, Field


class GroupParticipant(BaseModel):
    jid: str
    admin: Optional[str] = None


class GroupInfo(BaseModel):
    group_jid: str
    subject: str
    subject_owner: Optional[str] = None
    subject_time: Optional[int] = None
    creation: Optional[int] = None
    owner: Optional[str] = None
    desc: Optional[str] = None
    desc_id: Optional[str] = None
    restrict: Optional[bool] = None
    announce: Optional[bool] = None
    size: Optional[int] = None
    participants: list[GroupParticipant] = Field(default_factory=list)


class GroupSummary(BaseModel):
    jid: str
    name: Optional[str] = None
    size: Optional[int] = None
    participants: Optional[list[GroupParticipant]] = None


class CreateGroupRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=100)
    participants: list[str] = Field(..., min_length=1)
    description: Optional[str] = Field(None, max_length=1000)


class CreateGroupResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None
    subject: Optional[str] = None
    participants: Optional[list[str]] = None


class UpdateGroupSubjectRequest(BaseModel):
    group_jid: str
    subject: str = Field(..., min_length=1, max_length=100)


class UpdateGroupSubjectResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None
    subject: Optional[str] = None


class UpdateGroupDescriptionRequest(BaseModel):
    group_jid: str
    description: str = Field(..., max_length=1000)


class UpdateGroupDescriptionResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None


class UpdateGroupPictureRequest(BaseModel):
    group_jid: str
    image_url: str


class UpdateGroupPictureResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None


class GroupInfoResponse(BaseModel):
    group_jid: Optional[str] = None
    subject: Optional[str] = None
    subject_owner: Optional[str] = None
    subject_time: Optional[int] = None
    creation: Optional[int] = None
    owner: Optional[str] = None
    desc: Optional[str] = None
    desc_id: Optional[str] = None
    restrict: Optional[bool] = None
    announce: Optional[bool] = None
    size: Optional[int] = None
    participants: list[GroupParticipant] = Field(default_factory=list)


class GroupListResponse(BaseModel):
    groups: list[GroupSummary]


class GroupParticipantsResponse(BaseModel):
    group_jid: Optional[str] = None
    participants: list[GroupParticipant] = Field(default_factory=list)


class InviteCodeResponse(BaseModel):
    group_jid: Optional[str] = None
    invite_code: Optional[str] = None


class RevokeInviteResponse(BaseModel):
    group_jid: Optional[str] = None
    new_invite_code: Optional[str] = None


class AcceptInviteRequest(BaseModel):
    invite_code: str


class AcceptInviteResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None


class InviteInfoResponse(BaseModel):
    group_jid: Optional[str] = None
    subject: Optional[str] = None
    creation: Optional[int] = None
    owner: Optional[str] = None
    desc: Optional[str] = None
    size: Optional[int] = None


class UpdateGroupParticipantRequest(BaseModel):
    group_jid: str
    action: Literal["add", "remove", "promote", "demote"]
    participants: list[str] = Field(..., min_length=1)


class ParticipantUpdateResult(BaseModel):
    status: Optional[str] = None
    jid: Optional[str] = None
    content: Optional[str] = None


class UpdateGroupParticipantResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None
    action: Optional[str] = None
    results: list[ParticipantUpdateResult] = Field(default_factory=list)


class UpdateGroupSettingRequest(BaseModel):
    group_jid: str
    action: Literal["announcement", "not_announcement", "locked", "unlocked"]


class UpdateGroupSettingResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None
    setting: Optional[str] = None


class ToggleEphemeralRequest(BaseModel):
    group_jid: str
    expiration: Literal[0, 86400, 604800, 7776000]


class ToggleEphemeralResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None
    expiration: Optional[int] = None


class LeaveGroupResponse(BaseModel):
    status: Optional[str] = None
    group_jid: Optional[str] = None


# Advanced Messaging Models


class SendLocationRequest(BaseModel):
    number: str
    latitude: float
    longitude: float
    name: Optional[str] = None
    address: Optional[str] = None


class SendLocationResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class ContactCard(BaseModel):
    name: str
    phone: str


class SendContactRequest(BaseModel):
    number: str
    contacts: list[ContactCard]


class SendContactResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class ArchiveChatRequest(BaseModel):
    chat_jid: str
    archive: bool = True


class ArchiveChatResponse(BaseModel):
    status: Optional[str] = None
    chat_jid: Optional[str] = None
    archived: Optional[bool] = None


class BlockUserRequest(BaseModel):
    jid: str
    block: bool = True


class BlockUserResponse(BaseModel):
    status: Optional[str] = None
    jid: Optional[str] = None


class EditMessageRequest(BaseModel):
    to: str
    message_id: str
    text: str
    from_me: bool = True


class EditMessageResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class CheckWhatsAppRequest(BaseModel):
    numbers: list[str]


class WhatsAppNumberResult(BaseModel):
    number: str
    jid: Optional[str] = None
    exists: bool


class CheckWhatsAppResponse(BaseModel):
    results: list[WhatsAppNumberResult]


class UpdateProfileNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateProfileNameResponse(BaseModel):
    status: Optional[str] = None
    name: Optional[str] = None


class UpdateProfileStatusRequest(BaseModel):
    status: str = Field(..., max_length=500)


class UpdateProfileStatusResponse(BaseModel):
    status: Optional[str] = None


class UpdateProfilePictureRequest(BaseModel):
    image_url: str


class UpdateProfilePictureResponse(BaseModel):
    status: Optional[str] = None


class RemoveProfilePictureResponse(BaseModel):
    status: Optional[str] = None


class GetProfileResponse(BaseModel):
    jid: Optional[str] = None
    exists: Optional[bool] = None


class DeleteMessageRequest(BaseModel):
    chat_jid: str
    message_id: str
    from_me: bool = True


class DeleteMessageResponse(BaseModel):
    status: Optional[str] = None
    chat_jid: Optional[str] = None
    message_id: Optional[str] = None


class MarkReadRequest(BaseModel):
    chat_jid: str
    message_ids: list[str]


class MarkReadResponse(BaseModel):
    status: Optional[str] = None
    chat_jid: Optional[str] = None


class ContactInfo(BaseModel):
    jid: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    is_group: Optional[bool] = None


class ContactsListResponse(BaseModel):
    contacts: list[ContactInfo] = Field(default_factory=list)


class FetchProfilePictureRequest(BaseModel):
    jid: str


class FetchProfilePictureResponse(BaseModel):
    jid: Optional[str] = None
    url: Optional[str] = None


class SendStickerRequest(BaseModel):
    number: str
    sticker: str
    gif_playback: bool = False


class SendStickerResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class ButtonItem(BaseModel):
    type: Literal["reply", "url", "call", "copy"]
    display_text: str
    id: Optional[str] = None
    url: Optional[str] = None
    phone_number: Optional[str] = None
    copy_code: Optional[str] = None


class SendButtonsRequest(BaseModel):
    number: str
    title: str
    description: str
    footer: Optional[str] = None
    buttons: list[ButtonItem] = Field(..., min_length=1)
    thumbnail_url: Optional[str] = None


class SendButtonsResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class ListSectionRow(BaseModel):
    title: str
    description: Optional[str] = None
    row_id: str


class ListSection(BaseModel):
    title: str
    rows: list[ListSectionRow] = Field(..., min_length=1)


class SendListRequest(BaseModel):
    number: str
    title: str
    description: str
    footer: Optional[str] = None
    button_text: str
    sections: list[ListSection] = Field(..., min_length=1)


class SendListResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class SendStatusRequest(BaseModel):
    type: Literal["text", "image", "video"]
    content: str
    caption: Optional[str] = None
    background_color: Optional[str] = "#25D366"
    font: Optional[int] = 1
    status_jid_list: Optional[list[str]] = None
    all_contacts: bool = False


class SendStatusResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None
    recipient_count: Optional[int] = None


class PrivacySettings(BaseModel):
    readreceipts: Optional[str] = None
    profile: Optional[str] = None
    status: Optional[str] = None
    online: Optional[str] = None
    last: Optional[str] = None
    groupadd: Optional[str] = None


class FetchPrivacySettingsResponse(BaseModel):
    readreceipts: Optional[str] = None
    profile: Optional[str] = None
    status: Optional[str] = None
    online: Optional[str] = None
    last: Optional[str] = None
    groupadd: Optional[str] = None


class UpdatePrivacySettingsRequest(BaseModel):
    readreceipts: Optional[str] = None
    profile: Optional[str] = None
    status: Optional[str] = None
    online: Optional[str] = None
    last: Optional[str] = None
    groupadd: Optional[str] = None


class UpdatePrivacySettingsResponse(BaseModel):
    status: Optional[str] = None


class InstanceSettings(BaseModel):
    reject_call: bool = False
    msg_call: str = ""
    groups_ignore: bool = False
    always_online: bool = False
    read_messages: bool = False
    read_status: bool = False
    sync_full_history: bool = False


class InstanceSettingsRequest(BaseModel):
    reject_call: Optional[bool] = None
    msg_call: Optional[str] = None
    groups_ignore: Optional[bool] = None
    always_online: Optional[bool] = None
    read_messages: Optional[bool] = None
    read_status: Optional[bool] = None
    sync_full_history: Optional[bool] = None


class InstanceSettingsResponse(BaseModel):
    reject_call: Optional[bool] = None
    msg_call: Optional[str] = None
    groups_ignore: Optional[bool] = None
    always_online: Optional[bool] = None
    read_messages: Optional[bool] = None
    read_status: Optional[bool] = None
    sync_full_history: Optional[bool] = None
