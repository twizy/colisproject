"""
Expressions et agrégats financiers partagés.

Un seul endroit définit ce que « facturé », « encaissé » et « impayé »
veulent dire, pour que le tableau de bord, les exports et l'API donnent
exactement les mêmes chiffres que la page Crédits clients — qui, elle,
s'appuie sur ``InvoiceTable.total_due`` / ``InvoiceTable.balance``.
"""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, Greatest

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal('0'), output_field=MONEY)


def _wrap(expression):
    return ExpressionWrapper(expression, output_field=MONEY)


# Montant facturé d'une facture : poids x prix unitaire - remise, jamais négatif.
# Équivalent SQL de InvoiceTable.total_due.
TOTAL_DUE = Greatest(
    _wrap(F('package__weight') * F('amount') - F('discount')),
    ZERO,
    output_field=MONEY,
)

# Reste dû : le facturé moins ce qui a déjà été versé (acomptes compris).
# Équivalent SQL de InvoiceTable.balance.
BALANCE = Greatest(
    _wrap(F('package__weight') * F('amount') - F('discount') - F('amount_paid')),
    ZERO,
    output_field=MONEY,
)


def invoice_totals(invoices):
    """
    Retourne ``{'invoiced', 'collected', 'outstanding'}`` pour un queryset de
    factures.

    - ``invoiced``    : total facturé (remises déduites) ;
    - ``collected``   : argent réellement encaissé, acomptes sur factures
                        encore ouvertes compris ;
    - ``outstanding`` : reste dû, identique au total de la page Crédits.

    Sauf trop-perçu, ``collected + outstanding == invoiced``.
    """
    return invoices.aggregate(
        invoiced=Coalesce(Sum(TOTAL_DUE), ZERO),
        collected=Coalesce(Sum('amount_paid', output_field=MONEY), ZERO),
        outstanding=Coalesce(Sum(BALANCE), ZERO),
    )


def total_invoiced(invoices):
    """Total facturé (remises déduites) d'un queryset de factures."""
    return invoices.aggregate(v=Coalesce(Sum(TOTAL_DUE), ZERO))['v']
