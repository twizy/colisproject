"""
Handler d'exception global de l'API.

Objectif : quelle que soit l'erreur, la réponse contient toujours une clé
`detail` en texte lisible. Le client Android peut alors afficher
`error.detail` sans avoir à deviner la forme du corps :

    {"detail": "Le poids doit être supérieur à zéro.",
     "code": "validation_error",
     "errors": {"weight": ["Le poids doit être supérieur à zéro."]}}
"""
from django.db import IntegrityError
from django.http import Http404

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _first_message(payload):
    """Extrait le premier message lisible d'une structure d'erreurs DRF."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return _first_message(payload[0]) if payload else None
    if isinstance(payload, dict):
        for key in ('detail', 'non_field_errors'):
            if key in payload:
                return _first_message(payload[key])
        for value in payload.values():
            message = _first_message(value)
            if message:
                return message
    return None


def api_exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        return Response(
            {'detail': "Conflit de données : cet enregistrement existe déjà.",
             'code': 'integrity_error'},
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Erreur non gérée : DEBUG=True laisse Django afficher la trace.
        return None

    data = response.data
    detail = _first_message(data) or "Une erreur est survenue."

    payload = {
        'detail': detail,
        'code': getattr(exc, 'default_code', None) or 'error',
    }

    if isinstance(exc, Http404):
        payload['code'] = 'not_found'

    # Erreurs de validation : on garde le détail par champ pour qu'Android
    # puisse marquer le bon TextInputLayout.
    if isinstance(exc, ValidationError) and isinstance(data, dict):
        payload['code'] = 'validation_error'
        payload['errors'] = {k: v for k, v in data.items() if k != 'detail'}

    # Token expiré / invalide : on conserve le code de SimpleJWT, c'est lui
    # qui déclenche le rafraîchissement côté client.
    if isinstance(data, dict) and data.get('code'):
        payload['code'] = data['code']

    response.data = payload
    return response
