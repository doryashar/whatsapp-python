# Plugin System Architecture & Implementation Plan

**Status**: Planning Complete  
**Created**: 2026-03-02  
**Last Updated**: 2026-03-02  
**Priority**: High  

---

## Table of Contents

1. [Overview](#overview)
2. [Core Architecture](#core-architecture)
3. [Implementation Phases](#implementation-phases)
4. [Advanced Features (Planned)](#advanced-features-planned)
5. [File Structure](#file-structure)
6. [Risk Mitigation](#risk-mitigation)
7. [Success Metrics](#success-metrics)
8. [Timeline](#timeline)

---

## Overview

### Goal

Transform the OpenCode WhatsApp webhook integration into a **per-tenant plugin system** with full admin dashboard management, integrated into the main FastAPI process.

### Key Features

- ✅ **Per-Tenant Plugins**: Each tenant can enable/disable/configure plugins independently
- ✅ **Dedicated Plugin Directory**: Plugins stored in `src/plugins/` with clear structure
- ✅ **Admin Dashboard Integration**: Full UI for managing plugins
- ✅ **Plugin Installation**: Upload and install plugins via admin UI
- ✅ **Integrated Mode**: OpenCode runs inside main FastAPI process
- ✅ **API Versioning**: Semantic versioning for plugin compatibility

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Plugin Scope | Per-tenant | Allows tenant-specific customization |
| Storage | Dedicated `plugins/` directory | Clean separation, installable/removable |
| Admin Features | Enable/disable, configure, status, install/remove | Full lifecycle management |
| OpenCode Mode | Integrated (same process) | Shares resources, simpler deployment |
| Versioning | Semantic versioning | Compatibility checking, safe upgrades |

---

## Core Architecture

### 1. Directory Structure

```
src/
├── plugins/
│   ├── __init__.py              # Plugin manager, loader
│   ├── base.py                  # Plugin base class & interfaces
│   ├── registry.py              # Plugin discovery & registration
│   ├── manager.py               # Plugin lifecycle & tenant config
│   ├── versioning.py            # API version utilities
│   └── builtin/
│       └── opencode/
│           ├── __init__.py      # Plugin definition
│           ├── plugin.py        # OpenCodePlugin class
│           ├── handlers.py      # Webhook handlers (moved from scripts/)
│           ├── session.py       # Session manager (moved from scripts/)
│           ├── config.py        # Plugin config schema
│           ├── plugin.json      # Metadata (name, version, description)
│           └── default_prompt.md
```

### 2. Plugin Base Interface

**File**: `src/plugins/base.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, Any
from pydantic import BaseModel
from fastapi import APIRouter

PLUGIN_API_VERSION = "1.0.0"

class PluginConfig(BaseModel):
    """Base class for plugin configurations."""
    enabled: bool = False
    config: dict[str, Any] = {}

class PluginMetadata(BaseModel):
    """Plugin metadata from plugin.json"""
    name: str
    version: str
    api_version: str
    description: str
    author: str
    homepage: Optional[str] = None
    config_schema: dict[str, Any] = {}  # JSON Schema for config form

class PluginBase(ABC):
    """Base class for all plugins."""
    
    api_version: str = PLUGIN_API_VERSION
    metadata: PluginMetadata
    
    @classmethod
    def is_compatible(cls, system_version: str) -> bool:
        """Check if plugin is compatible with system plugin API version."""
        plugin_major = cls.api_version.split('.')[0]
        system_major = system_version.split('.')[0]
        return plugin_major == system_major
    
    @abstractmethod
    async def on_load(self) -> None:
        """Called when plugin is loaded into memory."""
        pass
    
    @abstractmethod
    async def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass
    
    async def on_tenant_enable(self, tenant_hash: str, config: dict) -> None:
        """Called when plugin is enabled for a tenant."""
        pass
    
    async def on_tenant_disable(self, tenant_hash: str) -> None:
        """Called when plugin is disabled for a tenant."""
        pass
    
    async def on_tenant_config_change(self, tenant_hash: str, config: dict) -> None:
        """Called when tenant's plugin config is updated."""
        pass
    
    async def on_event(
        self, 
        event_type: str, 
        data: dict, 
        tenant_hash: str
    ) -> Optional[dict]:
        """Called for each bridge event. Return modified data or None."""
        pass
    
    def register_routes(self) -> Optional[APIRouter]:
        """Return FastAPI router for plugin-specific endpoints."""
        return None
    
    def get_config_schema(self) -> dict:
        """Return JSON Schema for plugin configuration."""
        return self.metadata.config_schema
    
    def get_tenant_config(self, tenant_hash: str) -> dict:
        """Get tenant-specific configuration."""
        return {}
```

### 3. Plugin Manager

**File**: `src/plugins/manager.py`

```python
class PluginManager:
    """Manages plugin lifecycle and tenant configurations."""
    
    SYSTEM_API_VERSION = "1.0.0"
    
    def __init__(self, db: Database):
        self._plugins: dict[str, PluginBase] = {}
        self._tenant_configs: dict[str, dict[str, PluginConfig]] = {}
        self._db = db
    
    async def discover_plugins(self) -> list[str]:
        """Scan plugins/ directory for available plugins."""
        pass
    
    async def load_plugin(self, plugin_name: str) -> bool:
        """Load a plugin into memory with version compatibility check."""
        pass
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin from memory."""
        pass
    
    async def install_plugin(self, plugin_zip: UploadFile) -> dict:
        """Install plugin from uploaded zip file."""
        pass
    
    async def uninstall_plugin(self, plugin_name: str) -> bool:
        """Remove plugin from filesystem."""
        pass
    
    async def enable_for_tenant(
        self, 
        plugin_name: str, 
        tenant_hash: str, 
        config: dict = None
    ) -> None:
        """Enable plugin for specific tenant."""
        pass
    
    async def disable_for_tenant(
        self, 
        plugin_name: str, 
        tenant_hash: str
    ) -> None:
        """Disable plugin for specific tenant."""
        pass
    
    async def update_tenant_config(
        self,
        plugin_name: str,
        tenant_hash: str,
        config: dict
    ) -> None:
        """Update tenant's plugin configuration."""
        pass
    
    async def get_tenant_plugins(self, tenant_hash: str) -> list[dict]:
        """Get all plugins with their status for a tenant."""
        pass
    
    async def dispatch_event(
        self,
        event_type: str,
        data: dict,
        tenant_hash: str
    ) -> dict:
        """Dispatch event to all enabled plugins for tenant."""
        pass
    
    def get_plugin_routes(self) -> list[APIRouter]:
        """Get all plugin routers for mounting."""
        pass
```

### 4. Database Schema

**File**: `src/store/database.py` (additions)

```sql
-- Plugin configurations per tenant
CREATE TABLE plugin_configs (
    tenant_hash TEXT NOT NULL,
    plugin_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT FALSE,
    config JSON,  -- Plugin-specific configuration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_hash, plugin_name),
    FOREIGN KEY (tenant_hash) REFERENCES tenants(api_key_hash) ON DELETE CASCADE
);

-- Plugin state (installed plugins)
CREATE TABLE plugins (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    api_version TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON  -- Full plugin.json content
);
```

### 5. OpenCode Plugin

**File**: `src/plugins/builtin/opencode/plugin.json`

```json
{
  "name": "opencode",
  "version": "1.0.0",
  "api_version": "1.0.0",
  "description": "AI-powered auto-responses using OpenCode CLI",
  "author": "WhatsApp Python API",
  "homepage": "https://github.com/.../docs/opencode-integration.md",
  "icon": "robot",
  "config_schema": {
    "type": "object",
    "properties": {
      "prompt_file": {
        "type": "string",
        "title": "System Prompt File",
        "description": "Path to custom PROMPT.md file",
        "default": "PROMPT.md"
      },
      "timeout": {
        "type": "integer",
        "title": "Response Timeout",
        "description": "Maximum seconds to wait for AI response",
        "default": 120,
        "minimum": 10,
        "maximum": 300
      },
      "max_message_length": {
        "type": "integer",
        "title": "Max Response Length",
        "description": "Maximum characters in response before truncation",
        "default": 4000
      },
      "enable_media": {
        "type": "boolean",
        "title": "Process Media",
        "description": "Enable AI analysis of images, videos, documents",
        "default": true
      },
      "session_cleanup_days": {
        "type": "integer",
        "title": "Session Cleanup (Days)",
        "description": "Delete inactive sessions after X days",
        "default": 30
      },
      "ignore_group_messages": {
        "type": "boolean",
        "title": "Ignore Group Messages",
        "description": "Don't respond to messages in group chats",
        "default": false
      }
    },
    "required": ["timeout"]
  }
}
```

**File**: `src/plugins/builtin/opencode/plugin.py`

```python
from plugins.base import PluginBase, PluginMetadata
from .handlers import MessageHandler
from .session import SessionManager
from .config import OpenCodeConfig

class OpenCodePlugin(PluginBase):
    """OpenCode AI integration plugin."""
    
    metadata = PluginMetadata.parse_file("plugin.json")
    
    def __init__(self):
        self.session_managers: dict[str, SessionManager] = {}
        self.handlers: dict[str, MessageHandler] = {}
    
    async def on_load(self) -> None:
        """Initialize plugin."""
        self.prompt_template = self._load_prompt()
    
    async def on_unload(self) -> None:
        """Cleanup plugin resources."""
        for manager in self.session_managers.values():
            await manager.close()
    
    async def on_tenant_enable(
        self, 
        tenant_hash: str, 
        config: dict
    ) -> None:
        """Setup OpenCode for a tenant."""
        tenant_config = OpenCodeConfig(**config)
        
        # Create session manager for tenant
        session_manager = SessionManager(
            db_path=f"./data/plugins/opencode/sessions_{tenant_hash}.db"
        )
        await session_manager.init_db()
        self.session_managers[tenant_hash] = session_manager
        
        # Create message handler
        self.handlers[tenant_hash] = MessageHandler(
            session_manager=session_manager,
            config=tenant_config
        )
    
    async def on_tenant_disable(self, tenant_hash: str) -> None:
        """Cleanup tenant resources."""
        if tenant_hash in self.session_managers:
            await self.session_managers[tenant_hash].close()
            del self.session_managers[tenant_hash]
        if tenant_hash in self.handlers:
            del self.handlers[tenant_hash]
    
    async def on_tenant_config_change(
        self, 
        tenant_hash: str, 
        config: dict
    ) -> None:
        """Update tenant configuration."""
        if tenant_hash in self.handlers:
            self.handlers[tenant_hash].config = OpenCodeConfig(**config)
    
    async def on_event(
        self, 
        event_type: str, 
        data: dict, 
        tenant_hash: str
    ) -> Optional[dict]:
        """Process incoming WhatsApp events."""
        if event_type != "message":
            return None
        
        if tenant_hash not in self.handlers:
            return None
        
        handler = self.handlers[tenant_hash]
        
        # Process message asynchronously
        asyncio.create_task(
            handler.process_message(data)
        )
        
        return None  # Don't modify event
```

### 6. Integration in Main App

**File**: `src/main.py` (modifications)

```python
from plugins import plugin_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.init()
    await tenant_manager.restore_sessions()
    
    # Load and initialize plugins
    await plugin_manager.discover_plugins()
    for plugin_name in await plugin_manager.get_installed_plugins():
        await plugin_manager.load_plugin(plugin_name)
    
    yield
    
    # Shutdown
    await plugin_manager.unload_all()
    await tenant_manager.close()
    await db.close()

async def handle_bridge_event(
    event_type: str, 
    params: dict, 
    tenant_hash: Optional[str] = None
):
    # Existing webhook logic...
    
    # Dispatch to plugins
    if tenant_hash:
        modified_params = await plugin_manager.dispatch_event(
            event_type, 
            params, 
            tenant_hash
        )
        if modified_params:
            params = modified_params
    
    # Continue with webhook delivery...

# Mount plugin routes
for router in plugin_manager.get_plugin_routes():
    app.include_router(router)
```

### 7. Admin Dashboard

**File**: `src/admin/routes.py` (additions)

```python
@router.get("/plugins")
async def plugins_page(request: Request, _: None = Depends(require_admin_session)):
    """Plugins management page."""
    return HTMLResponse(content=render_plugins_page())

@router.get("/plugins/{plugin_name}")
async def plugin_detail(
    plugin_name: str,
    request: Request,
    _: None = Depends(require_admin_session)
):
    """Plugin detail page with configuration."""
    return HTMLResponse(content=render_plugin_detail(plugin_name))

# Admin API Endpoints
@router.get("/admin/api/plugins")
async def list_plugins(_: None = Depends(require_admin_session)):
    """List all installed plugins."""
    pass

@router.post("/admin/api/plugins/install")
async def install_plugin(
    file: UploadFile,
    _: None = Depends(require_admin_session)
):
    """Install plugin from uploaded zip."""
    pass

@router.delete("/admin/api/plugins/{plugin_name}")
async def uninstall_plugin(
    plugin_name: str,
    _: None = Depends(require_admin_session)
):
    """Uninstall plugin."""
    pass

@router.post("/admin/api/plugins/{plugin_name}/tenants/{tenant_hash}")
async def configure_plugin_for_tenant(
    plugin_name: str,
    tenant_hash: str,
    config: dict,
    _: None = Depends(require_admin_session)
):
    """Enable/configure plugin for specific tenant."""
    pass
```

### 8. Configuration

**File**: `src/config.py` (additions)

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Plugin configuration
    plugins_dir: Path = Field(
        default=Path("src/plugins/builtin"),
        alias="PLUGINS_DIR"
    )
    plugins_auto_discover: bool = Field(
        default=True,
        alias="PLUGINS_AUTO_DISCOVER"
    )
    plugins_allow_upload: bool = Field(
        default=True,
        alias="PLUGINS_ALLOW_UPLOAD"
    )
```

---

## Implementation Phases

### Phase 1: Core Plugin System ⭐

**Priority**: High  
**Estimated Time**: 6-8 hours  
**Dependencies**: None  

#### Tasks

- [ ] Create `src/plugins/` directory structure
- [ ] Implement `PluginBase` class with API versioning
- [ ] Implement `PluginMetadata` model with version field
- [ ] Implement `PluginManager` class:
  - [ ] Plugin discovery (scan directory)
  - [ ] Version compatibility checking
  - [ ] Load/unload lifecycle
  - [ ] Tenant config management
  - [ ] Event dispatch system
- [ ] Add database schema:
  - [ ] `plugins` table (installed plugins)
  - [ ] `plugin_configs` table (per-tenant configs)
- [ ] Integrate with `main.py`:
  - [ ] Lifespan hooks (startup/shutdown)
  - [ ] Event dispatch in `handle_bridge_event()`
  - [ ] Route mounting
- [ ] Add environment config
- [ ] Unit tests for core system

#### Deliverables

- Working plugin system framework
- Database migrations
- Basic test coverage
- API version validation working

---

### Phase 2: Admin Dashboard Integration ⭐

**Priority**: High  
**Estimated Time**: 8-10 hours  
**Dependencies**: Phase 1  

#### Tasks

- [ ] Add "Plugins" to admin sidebar navigation
- [ ] Create plugins list page:
  - [ ] Plugin cards with metadata
  - [ ] Install/Uninstall buttons
  - [ ] Enable/Disable toggles
- [ ] Create plugin detail page:
  - [ ] Metadata display
  - [ ] Per-tenant configuration table
  - [ ] Plugin-specific dashboard area
  - [ ] Activity logs
- [ ] Implement admin API endpoints:
  - [ ] `GET /admin/api/plugins` - List all
  - [ ] `GET /admin/api/plugins/{name}` - Details
  - [ ] `POST /admin/api/plugins/install` - Upload & install
  - [ ] `DELETE /admin/api/plugins/{name}` - Uninstall
  - [ ] `PATCH /admin/api/plugins/{name}` - Enable/disable
  - [ ] `POST /admin/api/plugins/{name}/tenants/{hash}` - Configure for tenant
  - [ ] `DELETE /admin/api/plugins/{name}/tenants/{hash}` - Disable for tenant
- [ ] Implement HTMX fragments:
  - [ ] Plugin list cards
  - [ ] Dynamic config forms (from JSON Schema)
  - [ ] Tenant config table
  - [ ] Status indicators
- [ ] Implement config form generator:
  - [ ] Parse JSON Schema
  - [ ] Generate HTML forms dynamically
  - [ ] Client-side validation
  - [ ] Server-side validation
- [ ] Integration tests for admin UI

#### Deliverables

- Complete admin UI for plugin management
- Working plugin installation flow
- Per-tenant configuration UI
- Dynamic form generation

---

### Phase 3: OpenCode Plugin Migration ⭐

**Priority**: High  
**Estimated Time**: 6-8 hours  
**Dependencies**: Phase 1 (can start parallel with Phase 2)  

#### Tasks

- [ ] Create `src/plugins/builtin/opencode/` structure
- [ ] Create `plugin.json` with metadata and config schema
- [ ] Migrate `scripts/session_manager.py`:
  - [ ] Move to `src/plugins/builtin/opencode/session.py`
  - [ ] Add tenant isolation (per-tenant DB paths)
  - [ ] Keep backward-compatible standalone mode
- [ ] Migrate `scripts/opencode_webhook_handler.py`:
  - [ ] Extract message processing logic to `handlers.py`
  - [ ] Remove FastAPI app code
  - [ ] Keep handler logic reusable
- [ ] Move `PROMPT.md` to `default_prompt.md` in plugin dir
- [ ] Implement `OpenCodePlugin` class:
  - [ ] `on_load()` - Initialize shared resources
  - [ ] `on_tenant_enable()` - Create session manager & handler
  - [ ] `on_tenant_disable()` - Cleanup tenant resources
  - [ ] `on_event()` - Process incoming messages
  - [ ] `register_routes()` - Plugin-specific endpoints
- [ ] Create `config.py` with Pydantic config model
- [ ] Migrate and update tests:
  - [ ] `tests/test_session_manager.py` → update imports
  - [ ] `tests/test_opencode_plugin.py` → new plugin tests
- [ ] Update `docs/opencode-integration.md`:
  - [ ] Add plugin mode instructions
  - [ ] Keep standalone mode docs
  - [ ] Add configuration guide

#### Deliverables

- Working OpenCode plugin
- Per-tenant session isolation
- Updated documentation
- All tests passing

---

### Phase 4: Plugin Installation & Lifecycle ⭐

**Priority**: High  
**Estimated Time**: 4-6 hours  
**Dependencies**: Phase 2  

#### Tasks

- [ ] Implement plugin upload endpoint:
  - [ ] Accept multipart/form-data
  - [ ] Validate zip file structure
  - [ ] Extract to plugins directory
  - [ ] Parse `plugin.json` metadata
- [ ] Add security validation:
  - [ ] Check for path traversal attacks
  - [ ] Validate required files exist
  - [ ] Check API version compatibility
  - [ ] Scan for malicious code patterns (basic)
- [ ] Implement plugin installation:
  - [ ] Copy to `plugins/` directory
  - [ ] Add to `plugins` database table
  - [ ] Call `on_load()` if auto-enable
- [ ] Implement plugin uninstallation:
  - [ ] Disable for all tenants
  - [ ] Call `on_unload()`
  - [ ] Remove from database
  - [ ] Delete plugin directory
- [ ] Add plugin enable/disable globally:
  - [ ] Toggle in `plugins` table
  - [ ] Call lifecycle hooks
- [ ] Add error handling:
  - [ ] Rollback on installation failure
  - [ ] Graceful degradation on plugin errors
  - [ ] Plugin crash recovery
- [ ] Testing:
  - [ ] Install/uninstall flow
  - [ ] Error scenarios
  - [ ] Concurrent operations

#### Deliverables

- Working plugin installation from UI
- Secure upload handling
- Plugin lifecycle management
- Error recovery mechanisms

---

### Phase 5: Polish & Documentation ⭐

**Priority**: High  
**Estimated Time**: 4-5 hours  
**Dependencies**: All previous phases (can overlap with Phase 4)  

#### Tasks

- [ ] Update main `README.md`:
  - [ ] Add plugin system overview
  - [ ] Link to plugin development guide
- [ ] Create `docs/plugin-development.md`:
  - [ ] Plugin API reference
  - [ ] Configuration schema guide
  - [ ] Event handling patterns
  - [ ] Testing plugins
  - [ ] Best practices
- [ ] Create `docs/plugin-api-versioning.md`:
  - [ ] Versioning strategy
  - [ ] Compatibility rules
  - [ ] Upgrade guide
- [ ] Create example plugin template:
  - [ ] `src/plugins/templates/example/`
  - [ ] Minimal working plugin
  - [ ] Well-documented code
- [ ] Performance testing:
  - [ ] Multiple plugins loaded
  - [ ] Event dispatch latency
  - [ ] Memory usage
- [ ] Security audit:
  - [ ] Plugin isolation
  - [ ] Config validation
  - [ ] File upload security
- [ ] Update existing documentation
- [ ] Create migration guide:
  - [ ] How to migrate standalone webhook to plugin
  - [ ] Configuration mapping

#### Deliverables

- Complete documentation
- Example plugin template
- Performance benchmarks
- Security checklist
- Migration guide

---

## Advanced Features (Planned)

**Status**: Planned but NOT implemented yet  
**Priority**: Low (future enhancement)  

### Future: Plugin Dependencies

#### Architecture

```python
# In plugin.json
{
  "dependencies": [
    {"name": "opencode", "version": ">=1.0.0,<2.0.0"}
  ]
}

# In PluginManager
async def check_dependencies(plugin_name: str) -> tuple[bool, list[str]]:
    """Check if plugin dependencies are satisfied."""
    pass

async def load_plugin_with_deps(plugin_name: str) -> bool:
    """Load plugin and its dependencies recursively."""
    # Topological sort
    # Handle circular dependencies
    pass
```

#### Implementation Notes

- Semantic versioning constraint resolver
- Dependency tree resolution
- Circular dependency detection
- Load order optimization
- Partial rollback on failure

---

### Future: Plugin Marketplace

#### Architecture

```python
class PluginMarketplace:
    """Interface with plugin marketplace/repository."""
    
    async def search_plugins(self, query: str) -> list[dict]:
        """Search available plugins."""
        pass
    
    async def download_plugin(self, plugin_name: str, version: str = None) -> Path:
        """Download plugin from marketplace."""
        pass
    
    async def check_updates(self) -> list[dict]:
        """Check for available plugin updates."""
        pass
```

#### UI Components

- Marketplace search page
- Plugin details from marketplace
- Install from marketplace button
- Update notifications

---

### Future: Hot Reload

#### Architecture

```python
class PluginReloader(FileSystemEventHandler):
    """Watch plugin directories for changes and reload."""
    
    async def _reload_plugin(self, plugin_name: str):
        """Reload plugin without restarting server."""
        # 1. Store tenant configs
        # 2. Unload plugin
        # 3. Clear module from sys.modules
        # 4. Reload plugin
        # 5. Restore tenant configs
        pass
```

#### Development Mode

- Enabled only when `DEBUG=true`
- Watch for file changes
- Graceful reload with state preservation
- Error recovery on syntax errors

---

### Future: Resource Quotas

#### Architecture

```python
@dataclass
class PluginQuota:
    """Resource limits for a plugin."""
    max_memory_mb: int = 100
    max_cpu_seconds: int = 5
    max_event_handlers: int = 10

class QuotaManager:
    """Enforce resource quotas on plugins."""
    
    async def enforce_memory_limit(self, plugin_name: str):
        """Check and enforce memory limit."""
        pass
    
    def track_event_handler(self, plugin_name: str, duration: float):
        """Track event handler execution time."""
        pass
```

#### Admin UI

- Plugin resource usage dashboard
- Set per-plugin quotas
- Usage graphs and alerts
- Auto-disable on quota violation

---

## File Structure

### New Files

```
src/plugins/
├── __init__.py                    # Plugin manager exports
├── base.py                        # PluginBase, PluginMetadata, PluginConfig
├── manager.py                     # PluginManager class
├── registry.py                    # Plugin discovery & registration
├── versioning.py                  # API version utilities
└── builtin/
    └── opencode/
        ├── __init__.py            # Export OpenCodePlugin
        ├── plugin.py              # OpenCodePlugin class
        ├── handlers.py            # Message processing
        ├── session.py             # SessionManager
        ├── config.py              # OpenCodeConfig Pydantic model
        ├── plugin.json            # Plugin metadata
        └── default_prompt.md      # Default system prompt

src/admin/
├── routes.py                      # Updated: Add plugins pages
└── fragments/
    └── plugins.py                 # Plugin HTMX fragments (NEW)

docs/
├── plugin-development.md          # Plugin developer guide (NEW)
├── plugin-api-versioning.md       # Versioning guide (NEW)
├── opencode-integration.md        # Updated for plugin mode
└── IMPLEMENTATION_SUMMARY.md      # Updated

tests/
├── test_plugin_base.py            # Plugin base tests (NEW)
├── test_plugin_manager.py         # Manager tests (NEW)
├── test_opencode_plugin.py        # OpenCode plugin tests (NEW)
└── test_session_manager.py        # Updated imports
```

### Modified Files

```
src/main.py                        # Add plugin lifecycle hooks
src/config.py                      # Add plugin config settings
src/store/database.py              # Add plugin tables
src/admin/routes.py                # Add plugins UI pages
requirements.txt                   # Add plugin dependencies
README.md                          # Add plugin system section
```

### Migrated Files

```
scripts/session_manager.py         → src/plugins/builtin/opencode/session.py
scripts/opencode_webhook_handler.py → src/plugins/builtin/opencode/handlers.py
PROMPT.md                          → src/plugins/builtin/opencode/default_prompt.md
```

### Kept for Backwards Compatibility

```
Dockerfile.webhook                 # Standalone deployment option
docker-compose.webhook.yml         # External service option
requirements-webhook.txt           # Standalone dependencies
tests/test_opencode_webhook_handler.py  # Keep for standalone mode
```

---

## Risk Mitigation

| Risk | Mitigation | Priority |
|------|------------|----------|
| Plugin crashes main app | Try-except in event dispatch, plugin isolation | High |
| Database migration failure | Migration rollback, backup before upgrade | High |
| Security vulnerability in plugins | Code signing, admin-only install, sandbox review | High |
| Performance degradation | Event handler timeouts, resource quotas (planned) | Medium |
| Version incompatibility | API versioning, compatibility checks | High |
| Plugin data loss on uninstall | Config backup, tenant notification | Medium |
| Circular dependencies | Topological sort, cycle detection (planned) | Low |

---

## Success Metrics

- ✅ **Functionality**: OpenCode works as plugin identical to standalone
- ✅ **Multi-tenancy**: Multiple tenants can use plugin independently
- ✅ **Usability**: Admin can install/configure plugins without code changes
- ✅ **Reliability**: Plugin errors don't crash main application
- ✅ **Performance**: Event dispatch adds <10ms latency
- ✅ **Security**: No unauthorized plugin installation
- ✅ **Test Coverage**: >80% coverage for plugin system
- ✅ **Documentation**: Complete guides for users and developers

---

## Timeline

### Sequential Estimate

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Core System | 6-8 hours | 6-8 hours |
| Phase 2: Admin Dashboard | 8-10 hours | 14-18 hours |
| Phase 3: OpenCode Migration | 6-8 hours | 20-26 hours |
| Phase 4: Installation | 4-6 hours | 24-32 hours |
| Phase 5: Documentation | 4-5 hours | 28-37 hours |

### Parallelized Estimate

| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1: Core System | 6-8 hours | Sequential |
| Phase 2: Admin Dashboard | 8-10 hours | Sequential |
| Phase 3: OpenCode Migration | 6-8 hours | Can start after Phase 1 |
| Phase 4: Installation | 4-6 hours | Can start after Phase 2 |
| Phase 5: Documentation | 4-5 hours | Can overlap with Phase 4 |
| **Total** | **~24-30 hours** | With parallelization |

---

## Next Steps

1. **Begin Phase 1**: Core plugin system implementation
2. **Test continuously**: TDD approach for reliability
3. **Document as we go**: Update docs in parallel
4. **Deliver incrementally**: Working system after each phase
5. **Gather feedback**: Iterate based on usage

---

## Notes

- Keep backwards compatibility with standalone OpenCode webhook handler
- All plugin code should be well-tested before merging
- Security is paramount - validate all plugin uploads
- Performance impact should be minimal (<10ms per event)
- Documentation should be clear for both users and developers

---

**Document Version**: 1.0  
**Last Review**: 2026-03-02  
**Next Review**: Start of implementation
