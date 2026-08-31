"""
Permissions de l'API — reprennent exactement les rôles du site web
(voir les helpers is_patron / is_staff_or_patron dans main/views.py).

    Patron  = is_superuser  -> accès total (finance, historiques, suppression)
    Staff   = is_staff      -> gestion quotidienne (colis, manifestes, paiements)
    Simple  = connecté      -> lecture seule
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsPatron(BasePermission):
    """Réservé au patron / propriétaire (is_superuser)."""
    message = "Permission refusée : réservé au patron."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class IsStaffOrPatron(BasePermission):
    """Staff de bureau ou patron."""
    message = "Permission refusée : réservé au personnel."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class ReadOnlyOrStaff(BasePermission):
    """
    Tout utilisateur connecté peut lire ; seuls staff/patron peuvent écrire.
    C'est la permission par défaut des ressources métier (manifestes, colis).
    """
    message = "Permission refusée : seul le personnel peut modifier cette ressource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_staff or user.is_superuser)


class ReadOnlyOrPatron(BasePermission):
    """Lecture pour tous les connectés ; écriture/suppression réservée au patron."""
    message = "Permission refusée : seul le patron peut modifier cette ressource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_superuser)
