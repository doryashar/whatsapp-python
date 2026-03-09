from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from ..bridge import BridgeError
from ..tenant import Tenant, tenant_manager
from ..telemetry import get_logger
from ..middleware import rate_limiter
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


class CreateTenantRequest:
    def __init__(self, name: str):
        self.name = name


class TenantResponse:
    def __init__(self, name: str, api_key: str, created_at: str):
        self.name = name
        self.api_key = api_key
        self.created_at = created_at


class TenantListResponse:
    def __init__(self, tenants: list[dict]):
        self.tenants = tenants


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
    logger.info(f"Update group setting: tenant={tenant.name}, group={request.group_jid}")
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
    logger.info(f"Toggle group ephemeral: tenant={tenant.name}, group={request.group_jid}")
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
