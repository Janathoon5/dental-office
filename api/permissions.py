from auditlog.context import auditlog_value
from rest_framework.permissions import BasePermission
from dental_office.roles import get_patient_profile, is_patient


class IsPatient(BasePermission):
    """Mobile API v1 is patient-only — staff use the web dashboard."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and is_patient(request.user)):
            return False
        # Every view here dereferences request.user.patient_profile, which
        # 500s when the link is missing and happily serves records for a
        # soft-deleted patient. Deny both instead (see get_patient_profile).
        if get_patient_profile(request.user) is None:
            return False
        # AuditlogMiddleware snapshots the actor for LogEntry attribution
        # *before* the view runs, at middleware entry — but DRF's JWT auth
        # only resolves request.user lazily, inside permission checks like
        # this one, which run after that snapshot was already taken. Without
        # this, every audit log entry for a JWT-authenticated write would
        # show actor=None. Safe to mutate here (not a new context manager):
        # the middleware's `with` block is already open for the whole
        # request, this just corrects the one value inside it.
        try:
            context_data = auditlog_value.get()
            context_data['actor'] = request.user
            auditlog_value.set(context_data)
        except LookupError:
            pass
        return True
