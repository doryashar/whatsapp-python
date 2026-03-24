import pytest


def _check_router(router_name, router):
    """Check that no static route is shadowed by an earlier parameterized route."""
    seen_param = []
    failures = []

    for route in router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set())
        if "{" in path:
            seen_param.append((path, methods))
        else:
            for param_path, param_methods in seen_param:
                shared_methods = methods & param_methods
                if shared_methods and path.startswith(
                    param_path.rsplit("/", 1)[0] + "/"
                ):
                    failures.append(
                        f"{router_name}: static {shared_methods} {path} registered after "
                        f"parameterized {param_methods} {param_path} -- will be shadowed"
                    )

    return failures


def test_admin_api_router_no_shadowing():
    from src.admin.routes import api_router

    failures = _check_router("admin_api_router", api_router)
    assert not failures, "\n".join(failures)


def test_admin_fragments_router_no_shadowing():
    from src.admin.routes import fragments_router

    failures = _check_router("admin_fragments_router", fragments_router)
    assert not failures, "\n".join(failures)


def test_admin_ui_router_no_shadowing():
    from src.admin.routes import router

    failures = _check_router("admin_ui_router", router)
    assert not failures, "\n".join(failures)


def test_api_v1_router_no_shadowing():
    from src.api.routes import router

    failures = _check_router("api_v1_router", router)
    assert not failures, "\n".join(failures)


def test_api_router_no_shadowing():
    from src.api.routes import router as api_v1_router

    failures = _check_router("api_router", api_v1_router)
    assert not failures, "\n".join(failures)
