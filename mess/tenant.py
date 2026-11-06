from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from .models import Mess, UserMessAccess, set_tenant_context, reset_tenant_context

class TenantMiddleware:
    """Resolve the logged-in user's mess access and enforce CO/OC read-only dashboards."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tokens = None
        request.mess_role = None
        request.accessible_messes = Mess.objects.none()
        request.active_mess = None
        if request.user.is_authenticated:
            if request.user.is_superuser:
                selected = request.session.get("active_mess_id")
                if selected:
                    mess = Mess.objects.filter(pk=selected, is_active=True).first()
                    if mess:
                        request.active_mess = mess
                        scope = [mess.pk]
                    else:
                        request.session.pop("active_mess_id", None)
                        scope = None
                else:
                    request.active_mess = Mess.objects.filter(is_active=True).order_by("name").first()
                    scope = [request.active_mess.pk] if request.active_mess else None
                request.mess_role = "SUPERUSER"
                request.accessible_messes = Mess.objects.filter(is_active=True)
                tokens = set_tenant_context(scope, request.active_mess.pk if request.active_mess else None)
            else:
                assignments = list(
                    UserMessAccess.objects.filter(user=request.user, mess__is_active=True)
                    .select_related("mess").order_by("mess__name")
                )
                roles = {a.role for a in assignments}
                if len(roles) == 1 and assignments and (
                    assignments[0].role == UserMessAccess.CO or len(assignments) == 1
                ):
                    request.mess_role = assignments[0].role
                    request.accessible_messes = Mess.objects.filter(pk__in=[a.mess_id for a in assignments])
                    if request.mess_role == UserMessAccess.CO:
                        scope = [a.mess_id for a in assignments]
                    else:
                        scope = [assignments[0].mess_id]
                        request.active_mess = assignments[0].mess
                    tokens = set_tenant_context(scope, request.active_mess.pk if request.active_mess else None)
                else:
                    scope = []
                    tokens = set_tenant_context(scope, None)
        try:
            if request.user.is_authenticated and not request.user.is_superuser:
                if not request.mess_role:
                    return HttpResponseForbidden(
                        "Your account has no valid mess assignment. Contact the Superuser."
                    )
                if request.mess_role in (UserMessAccess.CO, UserMessAccess.OC):
                    allowed = request.path == "/" or request.path.startswith("/login/") or request.path.startswith("/logout/")
                    if not allowed:
                        return HttpResponseForbidden(
                            "Your role is dashboard-only. Contact the Superuser if you need additional access."
                        )
            return self.get_response(request)
        finally:
            if tokens:
                reset_tenant_context(tokens)
