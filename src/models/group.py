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
    status: str
    group_jid: str
    subject: str
    participants: list[str]


class UpdateGroupSubjectRequest(BaseModel):
    group_jid: str
    subject: str = Field(..., min_length=1, max_length=100)


class UpdateGroupSubjectResponse(BaseModel):
    status: str
    group_jid: str
    subject: str


class UpdateGroupDescriptionRequest(BaseModel):
    group_jid: str
    description: str = Field(..., max_length=1000)


class UpdateGroupDescriptionResponse(BaseModel):
    status: str
    group_jid: str


class UpdateGroupPictureRequest(BaseModel):
    group_jid: str
    image_url: str


class UpdateGroupPictureResponse(BaseModel):
    status: str
    group_jid: str


class GroupInfoResponse(BaseModel):
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


class GroupListResponse(BaseModel):
    groups: list[GroupSummary]


class GroupParticipantsResponse(BaseModel):
    group_jid: str
    participants: list[GroupParticipant]


class InviteCodeResponse(BaseModel):
    group_jid: str
    invite_code: str


class RevokeInviteResponse(BaseModel):
    group_jid: str
    new_invite_code: str


class AcceptInviteRequest(BaseModel):
    invite_code: str


class AcceptInviteResponse(BaseModel):
    status: str
    group_jid: str


class InviteInfoResponse(BaseModel):
    group_jid: str
    subject: str
    creation: Optional[int] = None
    owner: Optional[str] = None
    desc: Optional[str] = None
    size: Optional[int] = None


class UpdateGroupParticipantRequest(BaseModel):
    group_jid: str
    action: Literal["add", "remove", "promote", "demote"]
    participants: list[str] = Field(..., min_length=1)


class ParticipantUpdateResult(BaseModel):
    status: str
    jid: str
    content: Optional[str] = None


class UpdateGroupParticipantResponse(BaseModel):
    status: str
    group_jid: str
    action: str
    results: list[ParticipantUpdateResult]


class UpdateGroupSettingRequest(BaseModel):
    group_jid: str
    action: Literal["announcement", "not_announcement", "locked", "unlocked"]


class UpdateGroupSettingResponse(BaseModel):
    status: str
    group_jid: str
    setting: str


class ToggleEphemeralRequest(BaseModel):
    group_jid: str
    expiration: Literal[0, 86400, 604800, 7776000]


class ToggleEphemeralResponse(BaseModel):
    status: str
    group_jid: str
    expiration: int


class LeaveGroupResponse(BaseModel):
    status: str
    group_jid: str
