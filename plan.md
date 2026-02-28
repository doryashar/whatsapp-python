# WhatsApp-Python & OpenClaw Compatibility Plan

## Executive Summary

**Status: NOT COMPATIBLE**

The `whatsapp-python` codebase and `openclaw/extensions/whatsapp` are architecturally incompatible. They serve different purposes and use different communication paradigms.

---

## Architecture Comparison

| Aspect | OpenClaw WhatsApp Extension | WhatsApp-Python |
|--------|----------------------------|-----------------|
| **Language** | TypeScript | Python + Node.js bridge |
| **Architecture** | Plugin expecting runtime injection | Standalone REST API server |
| **Communication** | Direct function calls to `PluginRuntime` | HTTP REST + WebSocket + JSON-RPC |
| **Auth Storage** | `~/.openclaw/credentials/whatsapp/{accountId}/` | `./data/auth/{tenant_hash}/` |
| **Multi-tenancy** | Account-based via config | Tenant-based via API keys |

---

## OpenClaw Extension Expected Interface

The extension at `openclaw/extensions/whatsapp` expects a `PluginRuntime` object with this interface:

### Authentication & Session
```typescript
interface WhatsAppRuntime {
  webAuthExists(authDir: string): Promise<boolean>;
  getWebAuthAgeMs(authDir: string): number | null;
  readWebSelfId(authDir: string): { e164: string | null; jid: string | null };
  logWebSelfId(authDir: string, runtime: RuntimeEnv, includeChannelPrefix: boolean): void;
  logoutWeb(params: { authDir?: string; isLegacyAuthDir?: boolean; runtime?: RuntimeEnv }): Promise<boolean>;
  getActiveWebListener(accountId?: string): ActiveWebListener | null;
}
```

### Login Flow
```typescript
interface WhatsAppRuntime {
  loginWeb(verbose: boolean, waitForConnection?, runtime: RuntimeEnv, accountId?: string): Promise<void>;
  startWebLoginWithQr(opts: { verbose?: boolean; timeoutMs?: number; force?: boolean; accountId?: string; runtime?: RuntimeEnv }): Promise<{ qrDataUrl?: string; message: string }>;
  waitForWebLogin(opts: { timeoutMs?: number; runtime?: RuntimeEnv; accountId?: string }): Promise<{ connected: boolean; message: string }>;
  createLoginTool(): ChannelAgentTool;
}
```

### Messaging
```typescript
interface WhatsAppRuntime {
  sendMessageWhatsApp(to: string, body: string, options: { verbose: boolean; mediaUrl?: string; gifPlayback?: boolean; accountId?: string }): Promise<{ messageId: string; toJid: string }>;
  sendPollWhatsApp(to: string, poll: PollInput, options: { verbose: boolean; accountId?: string }): Promise<{ messageId: string; toJid: string }>;
  handleWhatsAppAction(params: Record<string, unknown>, cfg: OpenClawConfig): Promise<AgentToolResult<unknown>>;
}
```

### Gateway/Monitoring
```typescript
interface WhatsAppRuntime {
  monitorWebChannel(verbose: boolean, listenerFactory?, keepAlive?: boolean, replyResolver?, runtime?: RuntimeEnv, abortSignal?: AbortSignal, tuning?: WebMonitorTuning): Promise<void>;
}
```

---

## WhatsApp-Python Provided Interface

WhatsApp-Python provides HTTP REST endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/status` | GET | Get connection status |
| `/api/login` | POST | Start login / get QR |
| `/api/logout` | POST | Logout |
| `/api/send` | POST | Send message |
| `/api/react` | POST | Send reaction |
| `/api/messages` | GET | List messages |
| `/api/webhooks` | GET/POST/DELETE | Manage webhooks |
| `/ws/events` | WebSocket | Real-time events |
| `/admin/tenants` | CRUD | Tenant management |

---

## Integration Options

### Option 1: HTTP Adapter (Recommended)
Create a TypeScript adapter in OpenClaw that calls whatsapp-python's REST API:

```typescript
// In openclaw, create a runtime that calls the HTTP API
class WhatsAppPythonRuntime {
  private baseUrl = "http://localhost:8080/api";
  
  async webAuthExists(authDir: string): Promise<boolean> {
    const resp = await fetch(`${this.baseUrl}/status`, { headers: { "X-API-Key": this.apiKey } });
    const data = await resp.json();
    return data.connection_state === "connected";
  }
  
  async startWebLoginWithQr(opts): Promise<{ qrDataUrl?: string; message: string }> {
    const resp = await fetch(`${this.baseUrl}/login`, { method: "POST", headers: { "X-API-Key": this.apiKey } });
    return await resp.json();
  }
  
  // ... implement other methods
}
```

### Option 2: Python Runtime Implementation
Implement the `PluginRuntime` interface in Python and expose via IPC or native addon.

### Option 3: Hybrid Bridge
Extend the Node.js bridge (`bridge/index.mjs`) to expose the runtime interface directly.

---

## Required Additions to WhatsApp-Python

To support full OpenClaw compatibility, add:

1. ~~**Poll Support** - `sendPollWhatsApp` method~~ ADDED
2. ~~**Typing Indicator** - `sendComposingTo` method~~ ADDED
3. ~~**Auth Age API** - Endpoint to check credential age~~ ADDED
4. ~~**Self Identity API** - Endpoint to get e164/jid~~ ADDED
5. **Group Metadata** - Participant lists, group info (TODO)
6. **Mention Handling** - `mentionedJids` in message events (TODO)
7. **Reply Context** - `replyToId`, `replyToBody`, `replyToSender` (TODO)
8. **Media Download** - Download media from received messages (TODO)

---

## Auth Directory Mapping

| System | Auth Directory Structure |
|--------|-------------------------|
| OpenClaw | `~/.openclaw/credentials/whatsapp/{accountId}/` |
| WhatsApp-Python | `./data/auth/{sha256(tenant_hash)[:16]}/` |

Both use Baileys `useMultiFileAuthState` format, so credentials are compatible if paths are mapped correctly.

---

## Next Steps

1. Fix bugs identified in `tofix.md`
2. Add missing API endpoints for OpenClaw compatibility
3. Create TypeScript HTTP adapter in OpenClaw
4. Add integration tests
