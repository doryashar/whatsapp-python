from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, Literal
from ..bridge import BridgeError
from ..tenant import Tenant, tenant_manager
from ..telemetry import get_logger
from ..middleware import rate_limiter
from ..utils import is_safe_webhook_url
from ..models import (
    SendMessageRequest,
    SendMessageResponse,
    SendReactionRequest,
    SendReactionResponse,
    LoginResponse,
    StatusResponse,
    LogoutResponse,
    MessageListResponse,
    SelfInfo,
    AddWebhookRequest,
    WebhookListResponse,
    WebhookOperationResponse,
    InboundMessage,
    SendPollRequest,
    SendPollResponse,
    SendTypingResponse,
    AuthExistsResponse,
    AuthAgeResponse,
    SelfIdResponse,
    CreateGroupRequest,
    CreateGroupResponse,
    UpdateGroupSubjectRequest,
    UpdateGroupSubjectResponse,
    UpdateGroupDescriptionRequest,
    UpdateGroupDescriptionResponse,
    UpdateGroupPictureRequest,
    UpdateGroupPictureResponse,
    GroupInfoResponse,
    GroupListResponse,
    GroupParticipantsResponse,
    InviteCodeResponse,
    RevokeInviteResponse,
    AcceptInviteRequest,
    AcceptInviteResponse,
    InviteInfoResponse,
    UpdateGroupParticipantRequest,
    UpdateGroupParticipantResponse,
    UpdateGroupSettingRequest,
    UpdateGroupSettingResponse,
    ToggleEphemeralRequest,
    ToggleEphemeralResponse,
    LeaveGroupResponse,
    GroupParticipant,
    GroupSummary,
    ParticipantUpdateResult,
    SendLocationRequest,
    SendLocationResponse,
    SendContactRequest,
    SendContactResponse,
    ArchiveChatRequest,
    ArchiveChatResponse,
    BlockUserRequest,
    BlockUserResponse,
    EditMessageRequest,
    EditMessageResponse,
    CheckWhatsAppRequest,
    CheckWhatsAppResponse,
    UpdateProfileNameRequest,
    UpdateProfileNameResponse,
    UpdateProfileStatusRequest,
    UpdateProfileStatusResponse,
    UpdateProfilePictureRequest,
    UpdateProfilePictureResponse,
    RemoveProfilePictureResponse,
    GetProfileResponse,
    DeleteMessageRequest,
    DeleteMessageResponse,
    MarkReadRequest,
    MarkReadResponse,
    ContactInfo,
    ContactsListResponse,
    FetchProfilePictureRequest,
    FetchProfilePictureResponse,
    SendStickerRequest,
    SendStickerResponse,
    ButtonItem,
    SendButtonsRequest,
    SendButtonsResponse,
    ListSectionRow,
    ListSection,
    SendListRequest,
    SendListResponse,
    SendStatusRequest,
    SendStatusResponse,
    PrivacySettings,
    FetchPrivacySettingsResponse,
    UpdatePrivacySettingsRequest,
    UpdatePrivacySettingsResponse,
    InstanceSettings,
    InstanceSettingsRequest,
    InstanceSettingsResponse,
)
from .auth import get_tenant, get_admin_key

logger = get_logger("whatsapp.api")

router = APIRouter(prefix="/api", tags=["WhatsApp"])
admin_router = APIRouter(prefix="/admin/v1", tags=["Admin"])


@router.get("/status", response_model=StatusResponse)
async def get_status(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Status check for tenant: {tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_status()
        logger.debug(
            f"Status result: state={result.get('connection_state')}, has_qr={result.get('has_qr')}"
        )
        return StatusResponse(
            connection_state=result.get("connection_state", "disconnected"),
            self_info=SelfInfo(**result["self"]) if result.get("self") else None,
            has_qr=result.get("has_qr", False),
        )
    except BridgeError as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Login requested for tenant: {tenant.name}")
    try:
        logger.debug(f"Getting/creating bridge for tenant: {tenant.name}")
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        logger.debug(f"Calling bridge.login()")
        result = await bridge.login()
        logger.info(
            f"Login result: status={result.get('status')}, state={result.get('connection_state')}, jid={result.get('jid')}"
        )
        return LoginResponse(
            status=result.get("status", "unknown"),
            qr=result.get("qr"),
            qr_data_url=result.get("qr_data_url"),
            connection_state=result.get("connection_state"),
            jid=result.get("jid"),
            phone=result.get("phone"),
            name=result.get("name"),
        )
    except BridgeError as e:
        logger.error(f"Login failed for tenant {tenant.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout", response_model=LogoutResponse)
async def logout(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Logout requested for tenant: {tenant.name}")
    try:
        if tenant.bridge:
            result = await tenant.bridge.logout()
            logger.info(f"Logout result: {result.get('status')}")
            return LogoutResponse(status=result.get("status", "logged_out"))
        logger.debug(f"No bridge for tenant {tenant.name}, returning not_connected")
        return LogoutResponse(status="not_connected")
    except BridgeError as e:
        logger.error(f"Logout failed for tenant {tenant.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_tenant),
):
    if tenant.message_store is None:
        raise HTTPException(status_code=500, detail="Message store not initialized")
    messages, total = tenant.message_store.list(limit=limit, offset=offset)
    return MessageListResponse(
        messages=[InboundMessage(**m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/messages")
async def clear_messages(tenant: Tenant = Depends(get_tenant)):
    if tenant.message_store is None:
        raise HTTPException(status_code=500, detail="Message store not initialized")
    tenant.message_store.clear()
    return {"status": "cleared"}


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send message requested: tenant={tenant.name}, to={request.to}")
    if request.media_url and not is_safe_webhook_url(request.media_url):
        raise HTTPException(status_code=400, detail="Invalid media_url: potential SSRF")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_message(
            to=request.to,
            text=request.text,
            media_url=request.media_url,
        )
        logger.info(
            f"Message sent: message_id={result.get('message_id')}, to={result.get('to')}"
        )
        return SendMessageResponse(
            message_id=result.get("message_id", "unknown"),
            to=result.get("to", request.to),
        )
    except BridgeError as e:
        logger.error(f"Send message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/react", response_model=SendReactionResponse)
async def send_reaction(
    request: SendReactionRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Send reaction: tenant={tenant.name}, chat={request.chat}, emoji={request.emoji}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_reaction(
            chat=request.chat,
            message_id=request.message_id,
            emoji=request.emoji,
            from_me=request.from_me,
        )
        logger.debug(f"Reaction result: {result.get('status')}")
        return SendReactionResponse(
            status=result.get("status", "reacted"),
            chat=result.get("chat", request.chat),
            message_id=request.message_id,
            emoji=request.emoji,
        )
    except BridgeError as e:
        logger.error(f"Send reaction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/poll", response_model=SendPollResponse)
async def send_poll(
    request: SendPollRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Send poll: tenant={tenant.name}, to={request.to}, name={request.name}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_poll(
            to=request.to,
            name=request.name,
            values=request.values,
            selectable_count=request.selectable_count,
        )
        logger.info(
            f"Poll sent: message_id={result.get('message_id')}, to={result.get('to')}"
        )
        return SendPollResponse(
            message_id=result.get("message_id", "unknown"),
            to=result.get("to", request.to),
        )
    except BridgeError as e:
        logger.error(f"Send poll failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/typing", response_model=SendTypingResponse)
async def send_typing(
    to: str = Query(..., description="Recipient phone number or JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Send typing: tenant={tenant.name}, to={to}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_typing(to=to)
        return SendTypingResponse(
            status=result.get("status", "typing"),
            to=result.get("to", to),
        )
    except BridgeError as e:
        logger.error(f"Send typing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/exists", response_model=AuthExistsResponse)
async def check_auth_exists(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Check auth exists: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.auth_exists()
        return AuthExistsResponse(exists=result.get("exists", False))
    except BridgeError as e:
        logger.error(f"Check auth exists failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/age", response_model=AuthAgeResponse)
async def get_auth_age(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Get auth age: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.auth_age()
        return AuthAgeResponse(age_ms=result.get("age_ms"))
    except BridgeError as e:
        logger.error(f"Get auth age failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/self", response_model=SelfIdResponse)
async def get_self_id(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Get self ID: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.self_id()
        return SelfIdResponse(
            jid=result.get("jid"),
            e164=result.get("e164"),
            name=result.get("name"),
        )
    except BridgeError as e:
        logger.error(f"Get self ID failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(tenant: Tenant = Depends(get_tenant)):
    return WebhookListResponse(urls=tenant.webhook_urls)


@router.post("/webhooks", response_model=WebhookOperationResponse)
async def add_webhook(
    request: AddWebhookRequest,
    tenant: Tenant = Depends(get_tenant),
):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="URL must start with http:// or https://"
        )
    if not is_safe_webhook_url(request.url):
        raise HTTPException(
            status_code=400,
            detail="Webhook URL points to internal or blocked address",
        )
    await tenant_manager.add_webhook(tenant, request.url)
    return WebhookOperationResponse(status="added", url=request.url)


@router.delete("/webhooks", response_model=WebhookOperationResponse)
async def remove_webhook(
    url: str = Query(..., description="Webhook URL to remove"),
    tenant: Tenant = Depends(get_tenant),
):
    if await tenant_manager.remove_webhook(tenant, url):
        return WebhookOperationResponse(status="removed", url=url)
    raise HTTPException(status_code=404, detail="Webhook URL not found")


@admin_router.post("/tenants")
async def create_tenant(
    name: str = Query(..., description="Tenant name"),
    _: str = Depends(get_admin_key),
):
    tenant, api_key = await tenant_manager.create_tenant(name)
    return {
        "name": tenant.name,
        "api_key": api_key,
        "created_at": tenant.created_at.isoformat(),
    }


@admin_router.get("/tenants")
async def list_tenants(_: str = Depends(get_admin_key)):
    tenants = []
    for t in tenant_manager.list_tenants():
        tenants.append(
            {
                "name": t.name,
                "created_at": t.created_at.isoformat(),
                "webhook_count": len(t.webhook_urls),
            }
        )
    return {"tenants": tenants}


@admin_router.delete("/tenants")
async def delete_tenant(
    api_key: str = Query(..., description="Tenant API key to delete"),
    _: str = Depends(get_admin_key),
):
    if await tenant_manager.delete_tenant(api_key):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Tenant not found")


@admin_router.get("/rate-limit/blocked")
async def list_blocked_ips(_: str = Depends(get_admin_key)):
    return {"blocked_ips": rate_limiter.get_blocked_ips()}


@admin_router.post("/rate-limit/block")
async def block_ip(
    ip: str = Query(..., description="IP address to block"),
    _: str = Depends(get_admin_key),
):
    rate_limiter.block_ip(ip, reason="admin")
    return {"status": "blocked", "ip": ip}


@admin_router.delete("/rate-limit/block")
async def unblock_ip(
    ip: str = Query(..., description="IP address to unblock"),
    _: str = Depends(get_admin_key),
):
    if rate_limiter.unblock_ip(ip):
        return {"status": "unblocked", "ip": ip}
    raise HTTPException(status_code=404, detail="IP not found in block list")


@admin_router.get("/rate-limit/stats")
async def rate_limit_stats(
    _: str = Depends(get_admin_key),
    ip: Optional[str] = Query(None, description="Get stats for specific IP"),
):
    return rate_limiter.get_stats(ip)


@admin_router.get("/rate-limit/failed-auth")
async def list_failed_auth_attempts(
    _: str = Depends(get_admin_key),
    ip: Optional[str] = Query(
        None, description="Get failed auth attempts for specific IP"
    ),
):
    return rate_limiter.get_failed_auth_attempts(ip)


@admin_router.delete("/rate-limit/failed-auth")
async def clear_failed_auth_attempts(
    ip: str = Query(..., description="IP address to clear failed attempts for"),
    _: str = Depends(get_admin_key),
):
    rate_limiter.clear_failed_auth(ip)
    return {"status": "cleared", "ip": ip}


# Group Management Endpoints (evolution-api compatible)


@router.post("/group/create")
async def create_group(
    request: CreateGroupRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Create group: tenant={tenant.name}, subject={request.subject}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_create(
            subject=request.subject,
            participants=request.participants,
            description=request.description,
        )
        return CreateGroupResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
            subject=result.get("subject"),
            participants=result.get("participants"),
        )
    except BridgeError as e:
        logger.error(f"Create group failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/updateSubject")
async def update_group_subject(
    group_jid: str = Query(..., description="Group JID"),
    subject: str = Query(..., description="New subject"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Update group subject: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_update_subject(
            group_jid=group_jid,
            subject=subject,
        )
        return UpdateGroupSubjectResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
            subject=result.get("subject"),
        )
    except BridgeError as e:
        logger.error(f"Update group subject failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/updateDescription")
async def update_group_description(
    group_jid: str = Query(..., description="Group JID"),
    description: str = Query(..., description="New description"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Update group description: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_update_description(
            group_jid=group_jid,
            description=description,
        )
        return UpdateGroupDescriptionResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
        )
    except BridgeError as e:
        logger.error(f"Update group description failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/updatePicture")
async def update_group_picture(
    group_jid: str = Query(..., description="Group JID"),
    image_url: str = Query(..., description="Image file path or URL"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Update group picture: tenant={tenant.name}, group={group_jid}")
    if image_url and not is_safe_webhook_url(image_url):
        raise HTTPException(status_code=400, detail="Invalid image_url: potential SSRF")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_update_picture(
            group_jid=group_jid,
            image_url=image_url,
        )
        return UpdateGroupPictureResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
        )
    except BridgeError as e:
        logger.error(f"Update group picture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/findGroupInfos")
async def get_group_info(
    group_jid: str = Query(..., description="Group JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Get group info: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_get_info(group_jid)
        return GroupInfoResponse(**result)
    except BridgeError as e:
        logger.error(f"Get group info failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/fetchAllGroups")
async def get_all_groups(
    get_participants: bool = Query(default=False, description="Include participants"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Fetch all groups: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_get_all(get_participants=get_participants)
        groups = []
        for g in result.get("groups", []):
            participants = None
            if get_participants:
                participants = [
                    GroupParticipant(jid=p.get("jid"), admin=p.get("admin"))
                    for p in g.get("participants", [])
                ]
            groups.append(
                GroupSummary(
                    jid=g.get("jid"),
                    name=g.get("name"),
                    size=g.get("size"),
                    participants=participants,
                )
            )
        return GroupListResponse(groups=groups)
    except BridgeError as e:
        logger.error(f"Fetch all groups failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/participants")
async def get_group_participants(
    group_jid: str = Query(..., description="Group JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Get group participants: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_get_participants(group_jid)
        participants = [
            GroupParticipant(jid=p.get("jid"), admin=p.get("admin"))
            for p in result.get("participants", [])
        ]
        return GroupParticipantsResponse(
            group_jid=group_jid,
            participants=participants,
        )
    except BridgeError as e:
        logger.error(f"Get group participants failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/inviteCode")
async def get_group_invite_code(
    group_jid: str = Query(..., description="Group JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Get group invite code: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_get_invite_code(group_jid)
        return InviteCodeResponse(
            group_jid=group_jid,
            invite_code=result.get("invite_code"),
        )
    except BridgeError as e:
        logger.error(f"Get group invite code failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/revokeInviteCode")
async def revoke_group_invite(
    group_jid: str = Query(..., description="Group JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Revoke group invite: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_revoke_invite(group_jid)
        return RevokeInviteResponse(
            group_jid=group_jid,
            new_invite_code=result.get("new_invite_code"),
        )
    except BridgeError as e:
        logger.error(f"Revoke group invite failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/acceptInviteCode")
async def accept_group_invite(
    invite_code: str = Query(..., description="Group invite code"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Accept group invite: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_accept_invite(invite_code)
        return AcceptInviteResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
        )
    except BridgeError as e:
        logger.error(f"Accept group invite failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/inviteInfo")
async def get_group_invite_info(
    invite_code: str = Query(..., description="Group invite code"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Get group invite info: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_get_invite_info(invite_code)
        return InviteInfoResponse(**result)
    except BridgeError as e:
        logger.error(f"Get group invite info failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/updateParticipant")
async def update_group_participant(
    request: UpdateGroupParticipantRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Update group participant: tenant={tenant.name}, "
        f"group={request.group_jid}, action={request.action}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_update_participant(
            group_jid=request.group_jid,
            action=request.action,
            participants=request.participants,
        )
        results = [
            ParticipantUpdateResult(
                status=r.get("status"),
                jid=r.get("jid"),
                content=r.get("content"),
            )
            for r in result.get("results", [])
        ]
        return UpdateGroupParticipantResponse(
            status="updated",
            group_jid=request.group_jid,
            action=request.action,
            results=results,
        )
    except BridgeError as e:
        logger.error(f"Update group participant failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/updateSetting")
async def update_group_setting(
    request: UpdateGroupSettingRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Update group setting: tenant={tenant.name}, group={request.group_jid}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_update_setting(
            group_jid=request.group_jid,
            action=request.action,
        )
        return UpdateGroupSettingResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
            setting=result.get("setting"),
        )
    except BridgeError as e:
        logger.error(f"Update group setting failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/toggleEphemeral")
async def toggle_group_ephemeral(
    request: ToggleEphemeralRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Toggle group ephemeral: tenant={tenant.name}, group={request.group_jid}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_toggle_ephemeral(
            group_jid=request.group_jid,
            expiration=request.expiration,
        )
        return ToggleEphemeralResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
            expiration=request.expiration,
        )
    except BridgeError as e:
        logger.error(f"Toggle group ephemeral failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/group/leaveGroup")
async def leave_group(
    group_jid: str = Query(..., description="Group JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Leave group: tenant={tenant.name}, group={group_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.group_leave(group_jid)
        return LeaveGroupResponse(
            status=result.get("status"),
            group_jid=result.get("group_jid"),
        )
    except BridgeError as e:
        logger.error(f"Leave group failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Advanced Messaging Endpoints


@router.post("/message/sendLocation")
async def send_location(
    request: SendLocationRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send location: tenant={tenant.name}, to={request.number}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_location(
            to=request.number,
            latitude=request.latitude,
            longitude=request.longitude,
            name=request.name,
            address=request.address,
        )
        return SendLocationResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Send location failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/sendContact")
async def send_contact(
    request: SendContactRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send contact: tenant={tenant.name}, to={request.number}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        contacts = [{"name": c.name, "phone": c.phone} for c in request.contacts]
        result = await bridge.send_contact(
            to=request.number,
            contacts=contacts,
        )
        return SendContactResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Send contact failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Chat Operations Endpoints


@router.post("/chat/archiveChat")
async def archive_chat(
    request: ArchiveChatRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Archive chat: tenant={tenant.name}, chat={request.chat_jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.archive_chat(
            chat_jid=request.chat_jid,
            archive=request.archive,
        )
        return ArchiveChatResponse(
            status=result.get("status"),
            chat_jid=result.get("chat_jid"),
            archived=result.get("archived"),
        )
    except BridgeError as e:
        logger.error(f"Archive chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/updateBlockStatus")
async def block_user(
    request: BlockUserRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Block user: tenant={tenant.name}, jid={request.jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.block_user(
            jid=request.jid,
            block=request.block,
        )
        return BlockUserResponse(
            status=result.get("status"),
            jid=result.get("jid"),
        )
    except BridgeError as e:
        logger.error(f"Block user failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/updateMessage")
async def edit_message(
    request: EditMessageRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Edit message: tenant={tenant.name}, to={request.to}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.edit_message(
            to=request.to,
            message_id=request.message_id,
            text=request.text,
            from_me=request.from_me,
        )
        return EditMessageResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Edit message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/whatsappNumbers")
async def check_whatsapp_numbers(
    request: CheckWhatsAppRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Check WhatsApp numbers: tenant={tenant.name}, count={len(request.numbers)}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.check_whatsapp(request.numbers)
        return CheckWhatsAppResponse(results=result.get("results", []))
    except BridgeError as e:
        logger.error(f"Check WhatsApp numbers failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Profile Operations Endpoints


@router.post("/chat/updateProfileName")
async def update_profile_name(
    request: UpdateProfileNameRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Update profile name: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.update_profile_name(request.name)
        return UpdateProfileNameResponse(
            status=result.get("status"),
            name=request.name,
        )
    except BridgeError as e:
        logger.error(f"Update profile name failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/updateProfileStatus")
async def update_profile_status(
    request: UpdateProfileStatusRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Update profile status: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.update_profile_status(request.status)
        return UpdateProfileStatusResponse(status=result.get("status"))
    except BridgeError as e:
        logger.error(f"Update profile status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/updateProfilePicture")
async def update_profile_picture(
    request: UpdateProfilePictureRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Update profile picture: tenant={tenant.name}")
    if request.image_url and not is_safe_webhook_url(request.image_url):
        raise HTTPException(status_code=400, detail="Invalid image_url: potential SSRF")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.update_profile_picture(request.image_url)
        return UpdateProfilePictureResponse(status=result.get("status"))
    except BridgeError as e:
        logger.error(f"Update profile picture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/removeProfilePicture")
async def remove_profile_picture(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Remove profile picture: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.remove_profile_picture()
        return RemoveProfilePictureResponse(status=result.get("status"))
    except BridgeError as e:
        logger.error(f"Remove profile picture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/fetchProfile")
async def get_profile(
    jid: Optional[str] = Query(None, description="User JID (optional)"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Get profile: tenant={tenant.name}, jid={jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_profile(jid)
        return GetProfileResponse(
            jid=result.get("jid"),
            exists=result.get("exists", False),
        )
    except BridgeError as e:
        logger.error(f"Get profile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/message/delete")
async def delete_message(
    request: DeleteMessageRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Delete message: tenant={tenant.name}, chat={request.chat_jid}, id={request.message_id}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.delete_message(
            to=request.chat_jid,
            message_id=request.message_id,
            from_me=request.from_me,
        )
        return DeleteMessageResponse(
            status=result.get("status"),
            chat_jid=result.get("chat_jid"),
            message_id=result.get("message_id"),
        )
    except BridgeError as e:
        logger.error(f"Delete message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/markRead")
async def mark_messages_read(
    request: MarkReadRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Mark read: tenant={tenant.name}, chat={request.chat_jid}, count={len(request.message_ids)}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.mark_read(
            to=request.chat_jid,
            message_ids=request.message_ids,
        )
        return MarkReadResponse(
            status=result.get("status"),
            chat_jid=request.chat_jid,
        )
    except BridgeError as e:
        logger.error(f"Mark read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts", response_model=ContactsListResponse)
async def get_contacts(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Get contacts: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_contacts()
        contacts = [
            ContactInfo(
                jid=c.get("jid"),
                name=c.get("name"),
                phone=c.get("phone"),
                is_group=c.get("is_group"),
            )
            for c in result.get("contacts", [])
        ]
        return ContactsListResponse(contacts=contacts)
    except BridgeError as e:
        logger.error(f"Get contacts failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-history")
async def sync_history(
    tenant: Tenant = Depends(get_tenant),
    limit: int = Query(default=50, ge=1, le=200, description="Messages per chat"),
):
    from ..utils.history import store_chat_messages

    logger.info(f"Manual history sync: tenant={tenant.name}, limit={limit}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.fetch_chat_history(limit_per_chat=limit)

        chats = result.get("chats", [])
        total_messages = result.get("total_messages", 0)

        stats = {"stored": 0, "duplicates": 0, "errors": 0}

        if tenant.message_store and tenant_manager._db:
            stats = await store_chat_messages(tenant, result, tenant_manager._db)

        logger.info(
            f"History sync complete for tenant {tenant.name}: "
            f"stored={stats['stored']}, duplicates={stats['duplicates']}"
        )

        return {
            "status": "synced",
            "chats_count": len(chats),
            "total_messages": total_messages,
            "stored": stats["stored"],
            "duplicates": stats["duplicates"],
            "errors": stats["errors"],
        }
    except BridgeError as e:
        logger.error(f"History sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/fetchProfilePicture")
async def fetch_profile_picture(
    request: FetchProfilePictureRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Fetch profile picture: tenant={tenant.name}, jid={request.jid}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_profile_picture(request.jid)
        url = result.get("url")
        if url and not is_safe_webhook_url(url):
            url = None
        return FetchProfilePictureResponse(
            jid=result.get("jid"),
            url=url,
        )
    except BridgeError as e:
        logger.error(f"Fetch profile picture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sticker", response_model=SendStickerResponse)
async def send_sticker(
    request: SendStickerRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send sticker: tenant={tenant.name}, to={request.number}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_sticker(
            to=request.number,
            sticker=request.sticker,
            gif_playback=request.gif_playback,
        )
        return SendStickerResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Send sticker failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buttons", response_model=SendButtonsResponse)
async def send_buttons(
    request: SendButtonsRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send buttons: tenant={tenant.name}, to={request.number}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        buttons_data = [
            {
                "type": btn.type,
                "display_text": btn.display_text,
                "id": btn.id,
                "url": btn.url,
                "phone_number": btn.phone_number,
                "copy_code": btn.copy_code,
            }
            for btn in request.buttons
        ]
        result = await bridge.send_buttons(
            to=request.number,
            title=request.title,
            description=request.description,
            footer=request.footer,
            buttons=buttons_data,
            thumbnail_url=request.thumbnail_url,
        )
        return SendButtonsResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Send buttons failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/list", response_model=SendListResponse)
async def send_list(
    request: SendListRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send list: tenant={tenant.name}, to={request.number}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        sections_data = [
            {
                "title": section.title,
                "rows": [
                    {
                        "title": row.title,
                        "description": row.description,
                        "row_id": row.row_id,
                    }
                    for row in section.rows
                ],
            }
            for section in request.sections
        ]
        result = await bridge.send_list(
            to=request.number,
            title=request.title,
            description=request.description,
            footer=request.footer,
            button_text=request.button_text,
            sections=sections_data,
        )
        return SendListResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
        )
    except BridgeError as e:
        logger.error(f"Send list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status", response_model=SendStatusResponse)
async def send_status(
    request: SendStatusRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send status: tenant={tenant.name}, type={request.type}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_status(
            type=request.type,
            content=request.content,
            caption=request.caption,
            background_color=request.background_color,
            font=request.font,
            status_jid_list=request.status_jid_list,
            all_contacts=request.all_contacts,
        )
        return SendStatusResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
            recipient_count=result.get("recipient_count"),
        )
    except BridgeError as e:
        logger.error(f"Send status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/privacy", response_model=FetchPrivacySettingsResponse)
async def fetch_privacy_settings(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Fetch privacy settings: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.fetch_privacy_settings()
        return FetchPrivacySettingsResponse(
            readreceipts=result.get("readreceipts"),
            profile=result.get("profile"),
            status=result.get("status"),
            online=result.get("online"),
            last=result.get("last"),
            groupadd=result.get("groupadd"),
        )
    except BridgeError as e:
        logger.error(f"Fetch privacy settings failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/privacy", response_model=UpdatePrivacySettingsResponse)
async def update_privacy_settings(
    request: UpdatePrivacySettingsRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Update privacy settings: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.update_privacy_settings(
            readreceipts=request.readreceipts,
            profile=request.profile,
            status=request.status,
            online=request.online,
            last=request.last,
            groupadd=request.groupadd,
        )
        return UpdatePrivacySettingsResponse(status=result.get("status"))
    except BridgeError as e:
        logger.error(f"Update privacy settings failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings", response_model=InstanceSettingsResponse)
async def get_settings(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Get settings: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_settings()
        return InstanceSettingsResponse(
            reject_call=result.get("reject_call"),
            msg_call=result.get("msg_call"),
            groups_ignore=result.get("groups_ignore"),
            always_online=result.get("always_online"),
            read_messages=result.get("read_messages"),
            read_status=result.get("read_status"),
            sync_full_history=result.get("sync_full_history"),
        )
    except BridgeError as e:
        logger.error(f"Get settings failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings", response_model=InstanceSettingsResponse)
async def update_settings(
    request: InstanceSettingsRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Update settings: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.update_settings(
            reject_call=request.reject_call,
            msg_call=request.msg_call,
            groups_ignore=request.groups_ignore,
            always_online=request.always_online,
            read_messages=request.read_messages,
            read_status=request.read_status,
            sync_full_history=request.sync_full_history,
        )
        return InstanceSettingsResponse(
            reject_call=result.get("reject_call"),
            msg_call=result.get("msg_call"),
            groups_ignore=result.get("groups_ignore"),
            always_online=result.get("always_online"),
            read_messages=result.get("read_messages"),
            read_status=result.get("read_status"),
            sync_full_history=result.get("sync_full_history"),
        )
    except BridgeError as e:
        logger.error(f"Update settings failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
