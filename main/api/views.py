"""
Vues de l'API Lukogo Express — toutes en classes (generics / APIView).

Convention d'erreur : on laisse DRF produire ses réponses standard
    400 {"champ": ["message"], "detail": "..."}
    401 {"detail": "...", "code": "token_not_valid"}
    403 {"detail": "..."}
    404 {"detail": "..."}
Un handler global (voir exceptions.py) normalise le tout en ajoutant une clé
"detail" lisible que le client Android affiche directement.
"""
import calendar
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import (
    Count, Sum, F, Q, Case, When, IntegerField, DecimalField, ExpressionWrapper,
)
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from ..models import (
    ManifestTable, PackageTable, InvoiceTable, MeasurePriceTable,
    Profile, PaymentHistory, DeliveryHistory,
)
from .permissions import IsPatron, IsStaffOrPatron, ReadOnlyOrStaff, ReadOnlyOrPatron
from .serializers import (
    money,
    LukogoTokenObtainPairSerializer,
    UserSerializer, UserUpdateSerializer, RegisterSerializer, ChangePasswordSerializer,
    ManifestSerializer, ManifestDetailSerializer, ManifestCreateSerializer,
    ManifestBulkActionSerializer,
    PackageSerializer, PackageCreateSerializer, PackageStatusSerializer,
    InvoiceSerializer, RecordPaymentSerializer, InvoicePaidStatusSerializer,
    MeasurePriceSerializer,
    PaymentHistorySerializer, DeliveryHistorySerializer,
    DashboardStatsSerializer, CreditCustomerSerializer,
)


# ============================================================
# Helpers
# ============================================================

def _parse_date(raw, fallback):
    try:
        return datetime.strptime(raw or '', '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return fallback


def _date_range(request, default_days=30):
    today = timezone.now().date()
    start = _parse_date(request.query_params.get('start_date'), today - timedelta(days=default_days - 1))
    end = _parse_date(request.query_params.get('end_date'), today)
    if start > end:
        start, end = end, start
    return start, end


def _weighted_sum(qs):
    """Somme de (poids x prix unitaire) — le vrai chiffre d'affaires facturé."""
    return qs.aggregate(v=Sum(
        ExpressionWrapper(
            F('package__weight') * F('amount'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    ))['v'] or Decimal('0')


# ============================================================
# Authentification
# ============================================================

class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/   {"username", "password"}
    ->  {"access", "refresh", "user": {...}}
    """
    permission_classes = [AllowAny]
    serializer_class = LukogoTokenObtainPairSerializer
    throttle_scope = 'login'


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Crée le compte puis renvoie directement une paire de tokens : Android
    enchaîne sur l'écran principal sans second appel réseau.
    """
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = LukogoTokenObtainPairSerializer.get_token(user)
        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user, context={'request': request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/   {"refresh": "<token>"}
    Met le refresh token en liste noire : il ne pourra plus servir.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.data.get('refresh')
        if not raw:
            return Response({'detail': "Le champ 'refresh' est requis."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(raw).blacklist()
        except TokenError:
            # Token déjà expiré ou déjà blacklisté : la déconnexion est
            # effective de toute façon, inutile de faire échouer le client.
            pass
        return Response({'detail': "Déconnecté."}, status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/ — profil de l'utilisateur connecté."""
    permission_classes = [IsAuthenticated]

    def get_object(self):
        Profile.objects.get_or_create(user=self.request.user)
        return self.request.user

    def get_serializer_class(self):
        return UserSerializer if self.request.method == 'GET' else UserUpdateSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        user = self.get_object()
        user.refresh_from_db()
        return Response(UserSerializer(user, context={'request': request}).data)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Le mot de passe a changé : on invalide les sessions JWT existantes.
        refresh = LukogoTokenObtainPairSerializer.get_token(request.user)
        return Response({
            'detail': "Mot de passe modifié avec succès.",
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


# ============================================================
# Manifestes
# ============================================================

class ManifestListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/manifests/     ?search=&is_full=&ordering=
    POST /api/manifests/     (staff/patron)
    """
    permission_classes = [ReadOnlyOrStaff]
    filterset_fields = ['is_full', 'created_by']
    search_fields = ['code', 'vehicle_plate', 'driver_name', 'departure_point', 'arrival_point']
    ordering_fields = ['created_at', 'code', 'departure_time']

    def get_queryset(self):
        return (
            ManifestTable.objects
            .select_related('created_by')
            .prefetch_related('packages__invoice')
            .annotate(packages_count=Count('packages', distinct=True))
            .order_by('-created_at')
        )

    def get_serializer_class(self):
        return ManifestCreateSerializer if self.request.method == 'POST' else ManifestSerializer


class ManifestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/manifests/<id>/   manifeste + colis
    PATCH  /api/manifests/<id>/   (staff/patron)
    DELETE /api/manifests/<id>/   (patron uniquement)
    """
    serializer_class = ManifestDetailSerializer

    def get_queryset(self):
        return (
            ManifestTable.objects
            .select_related('created_by')
            .prefetch_related('packages__invoice')
            .annotate(packages_count=Count('packages', distinct=True))
        )

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [ReadOnlyOrPatron()]
        return [ReadOnlyOrStaff()]

    def destroy(self, request, *args, **kwargs):
        manifest = self.get_object()
        code = manifest.code
        manifest.delete()
        return Response({'detail': f"Manifeste {code} supprimé."}, status=status.HTTP_200_OK)


class ManifestPackagesView(generics.ListAPIView):
    """GET /api/manifests/<id>/packages/"""
    permission_classes = [IsAuthenticated]
    serializer_class = PackageSerializer
    search_fields = ['owner_name', 'receiver_name', 'description']
    filterset_fields = ['status']

    def get_queryset(self):
        manifest = get_object_or_404(ManifestTable, pk=self.kwargs['pk'])
        return (
            manifest.packages
            .select_related('invoice', 'manifest', 'created_by')
            .order_by('-created_at')
        )


class ManifestBulkActionView(APIView):
    """
    POST /api/manifests/<id>/bulk-action/   {"action": 1|2|3}
    Reprend main.views.manifest_bulk_action, historique de livraison inclus.
    """
    permission_classes = [IsStaffOrPatron]

    @transaction.atomic
    def post(self, request, pk):
        serializer = ManifestBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']

        manifest = get_object_or_404(ManifestTable, pk=pk)
        pkgs = PackageTable.objects.filter(manifest=manifest)

        if action == 1:
            now = timezone.now()
            to_deliver = list(pkgs.filter(status__in=['in_transit', 'pending']))
            pkgs.filter(status__in=['in_transit', 'pending']).update(status='delivered', taken_at=now)
            DeliveryHistory.objects.bulk_create([
                DeliveryHistory(
                    package=pkg,
                    received_by=pkg.receiver_name,
                    recorded_by=request.user,
                    delivered_at=now,
                )
                for pkg in to_deliver
            ])
            detail = f"Manifeste {manifest.code} — {len(to_deliver)} colis marqués comme livrés."
        elif action == 2:
            updated = pkgs.filter(status='in_transit').update(status='pending')
            detail = f"Manifeste {manifest.code} — {updated} colis mis en attente de récupération."
        else:
            updated = pkgs.exclude(status='delivered').update(status='cancelled')
            detail = f"Manifeste {manifest.code} — {updated} colis annulés."

        return Response({
            'detail': detail,
            'manifest': ManifestDetailSerializer(manifest, context={'request': request}).data,
        })


class ManifestCompleteView(APIView):
    """POST /api/manifests/<id>/complete/ — clôture le manifeste (is_full)."""
    permission_classes = [IsStaffOrPatron]

    def post(self, request, pk):
        manifest = get_object_or_404(ManifestTable, pk=pk)
        manifest.is_full = True
        if not manifest.arrival_time:
            manifest.arrival_time = timezone.localtime().time()
        manifest.save(update_fields=['is_full', 'arrival_time'])
        return Response({
            'detail': f"Manifeste {manifest.code} clôturé.",
            'manifest': ManifestSerializer(manifest, context={'request': request}).data,
        })


class ManifestCreditsView(APIView):
    """
    GET /api/manifests/<id>/credits/
    Répartit les colis du manifeste entre payés et à crédit (voir la vue web
    manifest_credits) avec les totaux correspondants.
    """
    permission_classes = [IsStaffOrPatron]

    def get(self, request, pk):
        manifest = get_object_or_404(ManifestTable, pk=pk)
        packages = manifest.packages.select_related('invoice')

        paid, credit = [], []
        total_paid, total_credit = Decimal('0'), Decimal('0')

        for pkg in packages:
            invoice = getattr(pkg, 'invoice', None)
            line_total = (pkg.weight or Decimal('0')) * (pkg.price or Decimal('0'))
            entry = {
                'package': PackageSerializer(pkg, context={'request': request}).data,
                'total': money(line_total),
                'balance': money(invoice.balance) if invoice else money(line_total),
            }
            if invoice and invoice.paid:
                paid.append(entry)
                total_paid += line_total
            else:
                credit.append(entry)
                total_credit += line_total

        return Response({
            'manifest': ManifestSerializer(manifest, context={'request': request}).data,
            'paid_list': paid,
            'credit_list': credit,
            'total_paid': money(total_paid),
            'total_credit': money(total_credit),
            'total_global': money(total_paid + total_credit),
        })


# ============================================================
# Colis
# ============================================================

class PackageListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/packages/   ?status=&manifest=&search=&ordering=
    POST /api/packages/   (staff/patron) — crée aussi la facture
    """
    permission_classes = [ReadOnlyOrStaff]
    filterset_fields = ['status', 'manifest', 'measure', 'created_by']
    search_fields = ['owner_name', 'receiver_name', 'description', 'manifest__code']
    ordering_fields = ['created_at', 'taken_at', 'weight', 'price']

    def get_queryset(self):
        qs = PackageTable.objects.select_related('manifest', 'invoice', 'created_by').order_by('-created_at')
        start = self.request.query_params.get('start_date')
        end = self.request.query_params.get('end_date')
        if start or end:
            s, e = _date_range(self.request)
            qs = qs.filter(created_at__date__range=[s, e])
        return qs

    def get_serializer_class(self):
        return PackageCreateSerializer if self.request.method == 'POST' else PackageSerializer


class PackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH (staff) / DELETE (patron) /api/packages/<id>/"""
    serializer_class = PackageSerializer

    def get_queryset(self):
        return PackageTable.objects.select_related('manifest', 'invoice', 'created_by')

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [ReadOnlyOrPatron()]
        return [ReadOnlyOrStaff()]

    def destroy(self, request, *args, **kwargs):
        pkg = self.get_object()
        pkg_id = pkg.id
        pkg.delete()
        return Response({'detail': f"Colis #{pkg_id} supprimé."}, status=status.HTTP_200_OK)


class PackageStatusView(APIView):
    """
    POST /api/packages/<id>/status/   {"status": "delivered", "received_by": "..."}
    Passer à 'delivered' écrit une ligne dans l'historique de livraison.
    """
    permission_classes = [IsStaffOrPatron]

    @transaction.atomic
    def post(self, request, pk):
        serializer = PackageStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        received_by = (serializer.validated_data.get('received_by') or '').strip()

        pkg = get_object_or_404(PackageTable, pk=pk)

        if new_status == 'delivered':
            pkg.status = 'delivered'
            pkg.taken_at = timezone.now()
            pkg.save(update_fields=['status', 'taken_at'])
            DeliveryHistory.objects.create(
                package=pkg,
                received_by=received_by or pkg.receiver_name,
                recorded_by=request.user,
                delivered_at=pkg.taken_at,
            )
        else:
            pkg.status = new_status
            pkg.save(update_fields=['status'])

        return Response({
            'detail': "Statut mis à jour.",
            'package': PackageSerializer(pkg, context={'request': request}).data,
        })


# ============================================================
# Factures & paiements
# ============================================================

class InvoiceListView(generics.ListAPIView):
    """
    GET /api/invoices/   ?paid=true|false&search=

    La réponse paginée porte en plus une clé `summary` avec les totaux payés /
    impayés, ce qui évite un second aller-retour pour l'en-tête de l'écran.
    """
    permission_classes = [IsStaffOrPatron]
    serializer_class = InvoiceSerializer
    filterset_fields = ['paid']
    search_fields = ['package__owner_name', 'package__receiver_name', 'package__description']
    ordering_fields = ['date_issued', 'amount']

    def get_queryset(self):
        return InvoiceTable.objects.select_related('package', 'package__manifest').order_by('-date_issued')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # Les totaux tiennent compte de la recherche mais PAS du filtre
        # paid=… : sinon filtrer sur « impayés » ferait tomber le total payé
        # à zéro et l'en-tête deviendrait trompeur.
        base = SearchFilter().filter_queryset(request, self.get_queryset(), self)
        paid_qs = base.filter(paid=True)
        unpaid_qs = base.filter(paid=False)

        response.data['summary'] = {
            'paid_count': paid_qs.count(),
            'unpaid_count': unpaid_qs.count(),
            'paid_total': money(_weighted_sum(paid_qs)),
            'unpaid_total': money(_weighted_sum(unpaid_qs)),
            'balance_total': money(
                unpaid_qs.aggregate(v=Sum(
                    ExpressionWrapper(
                        F('package__weight') * F('amount') - F('discount') - F('amount_paid'),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ))['v'] or Decimal('0')
            ),
        }
        return response


class InvoiceDetailView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/invoices/<id>/"""
    permission_classes = [IsStaffOrPatron]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return InvoiceTable.objects.select_related('package', 'package__manifest')


class InvoicePayView(APIView):
    """
    POST /api/invoices/<id>/pay/   {"amount": 5000}
    Versement partiel ou total, plafonné au solde restant, tracé dans
    PaymentHistory — même règle que main.views.record_payment.
    """
    permission_classes = [IsStaffOrPatron]

    @transaction.atomic
    def post(self, request, pk):
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.validated_data['amount']

        invoice = get_object_or_404(
            InvoiceTable.objects.select_for_update().select_related('package'), pk=pk
        )
        balance = invoice.balance
        if balance <= Decimal('0'):
            return Response({'detail': "Cette facture est déjà soldée."},
                            status=status.HTTP_400_BAD_REQUEST)

        payment = min(payment, balance)          # jamais plus que le solde
        invoice.amount_paid += payment
        invoice.paid = invoice.amount_paid >= invoice.total_due
        invoice.save()

        PaymentHistory.objects.create(
            invoice=invoice,
            amount=payment,
            balance_after=invoice.balance,
            is_full=invoice.paid,
            recorded_by=request.user,
        )

        return Response({
            'detail': "Paiement enregistré.",
            'amount_recorded': payment,
            'invoice': InvoiceSerializer(invoice, context={'request': request}).data,
        })


class InvoiceStatusView(APIView):
    """POST /api/invoices/<id>/status/   {"paid": true} — solde ou rouvre la facture."""
    permission_classes = [IsStaffOrPatron]

    @transaction.atomic
    def post(self, request, pk):
        serializer = InvoicePaidStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        paid = serializer.validated_data['paid']

        invoice = get_object_or_404(
            InvoiceTable.objects.select_for_update().select_related('package'), pk=pk
        )
        balance_before = invoice.balance
        invoice.paid = paid
        if paid:
            invoice.date_issued = timezone.now()
            invoice.amount_paid = invoice.total_due
        invoice.save()

        if paid and balance_before > Decimal('0'):
            PaymentHistory.objects.create(
                invoice=invoice,
                amount=balance_before,
                balance_after=invoice.balance,
                is_full=True,
                recorded_by=request.user,
            )

        return Response({
            'detail': "Statut de la facture mis à jour.",
            'invoice': InvoiceSerializer(invoice, context={'request': request}).data,
        })


class CreditsView(APIView):
    """
    GET /api/credits/   ?q=<nom du client>
    Dettes regroupées par client, comme la page « Crédits » du site.
    """
    permission_classes = [IsStaffOrPatron]

    def get(self, request):
        search = (request.query_params.get('q') or '').strip()

        qs = (
            InvoiceTable.objects
            .filter(paid=False)
            .select_related('package', 'package__manifest')
            .order_by('package__owner_name', '-package__taken_at')
        )
        if search:
            qs = qs.filter(package__owner_name__icontains=search)

        customers = {}
        for invoice in qs:
            if invoice.balance <= Decimal('0'):
                continue
            entry = customers.setdefault(
                invoice.package.owner_name,
                {'owner_name': invoice.package.owner_name,
                 'total_debt': Decimal('0'), 'count': 0, 'invoices': []},
            )
            entry['invoices'].append(invoice)
            entry['total_debt'] += invoice.balance
            entry['count'] += 1

        rows = [customers[name] for name in sorted(customers)]
        data = CreditCustomerSerializer(rows, many=True, context={'request': request}).data

        return Response({
            'total_customers': len(rows),
            'total_items': sum(r['count'] for r in rows),
            'grand_total': money(sum((r['total_debt'] for r in rows), Decimal('0'))),
            'customers': data,
        })


# ============================================================
# Historiques
# ============================================================

class PaymentHistoryListView(generics.ListAPIView):
    """
    GET /api/history/payments/   (patron)

    La réponse paginée porte en plus une clé `summary` avec le total encaissé,
    comme la page web « payment-history ». Le total couvre TOUS les versements
    correspondant à la recherche, pas seulement la page affichée.
    """
    permission_classes = [IsPatron]
    serializer_class = PaymentHistorySerializer
    search_fields = [
        'invoice__package__owner_name',
        'invoice__package__receiver_name',
        'invoice__package__description',
    ]
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        return (
            PaymentHistory.objects
            .select_related('invoice', 'invoice__package', 'recorded_by')
            .order_by('-created_at')
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # filter_queryset applique la recherche : le total suit donc ce que
        # l'utilisateur a filtré, ce qui est le comportement attendu ici.
        qs = self.filter_queryset(self.get_queryset())
        totals = qs.aggregate(
            total=Sum('amount'),
            count=Count('id'),
            full=Count(Case(When(is_full=True, then=1), output_field=IntegerField())),
        )
        response.data['summary'] = {
            'count': totals['count'] or 0,
            'total_amount': money(totals['total'] or Decimal('0')),
            'full_count': totals['full'] or 0,
            'partial_count': (totals['count'] or 0) - (totals['full'] or 0),
        }
        return response


class DeliveryHistoryListView(generics.ListAPIView):
    """GET /api/history/deliveries/   (staff/patron)"""
    permission_classes = [IsStaffOrPatron]
    serializer_class = DeliveryHistorySerializer
    search_fields = ['received_by', 'package__owner_name', 'package__description']
    ordering_fields = ['delivered_at']

    def get_queryset(self):
        return (
            DeliveryHistory.objects
            .select_related('package', 'package__manifest', 'recorded_by')
            .order_by('-delivered_at')
        )


class DeliveryHistoryUpdateView(generics.UpdateAPIView):
    """PATCH /api/history/deliveries/<id>/   {"received_by": "..."}"""
    permission_classes = [IsStaffOrPatron]
    serializer_class = DeliveryHistorySerializer
    queryset = DeliveryHistory.objects.select_related('package', 'recorded_by')


# ============================================================
# Tableaux de bord
# ============================================================

class DashboardStatsView(APIView):
    """
    GET /api/stats/dashboard/   ?preset=7d|30d|month|custom&start_date=&end_date=
    Équivalent API de la page d'accueil, séries du graphique comprises.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        preset = request.query_params.get('preset', '30d')

        if preset == '7d':
            start, end = today - timedelta(days=6), today
        elif preset == 'month':
            start, end = today.replace(day=1), today
        elif preset == 'custom':
            start, end = _date_range(request)
        else:
            preset = '30d'
            start, end = today - timedelta(days=29), today

        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

        rows = (
            PackageTable.objects
            .filter(created_at__date__range=[start, end])
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                total=Count('id'),
                delivered=Count(Case(When(status='delivered', then=1), output_field=IntegerField())),
                not_delivered=Count(
                    Case(When(status__in=['pending', 'in_transit'], then=1), output_field=IntegerField())
                ),
            )
            .order_by('day')
        )
        by_day = {r['day']: r for r in rows}

        payload = {
            'total_manifests': ManifestTable.objects.count(),
            'total_packages': PackageTable.objects.count(),
            'total_users': User.objects.count(),
            'total_invoices': InvoiceTable.objects.count(),
            'unpaid_invoices': InvoiceTable.objects.filter(paid=False).count(),
            'delivered_packages': PackageTable.objects.filter(status='delivered').count(),
            'pending_packages': PackageTable.objects.filter(status='pending').count(),
            'in_transit_packages': PackageTable.objects.filter(status='in_transit').count(),
            'cancelled_packages': PackageTable.objects.filter(status='cancelled').count(),
            # Argent réellement encaissé (versements partiels compris), pas le
            # simple prix unitaire sommé.
            'total_income': InvoiceTable.objects.aggregate(v=Sum('amount_paid'))['v'] or Decimal('0'),
            'chart_labels': [d.strftime('%d/%m') for d in days],
            'chart_total': [by_day.get(d, {}).get('total', 0) for d in days],
            'chart_delivered': [by_day.get(d, {}).get('delivered', 0) for d in days],
            'chart_not_delivered': [by_day.get(d, {}).get('not_delivered', 0) for d in days],
        }
        response = DashboardStatsSerializer(payload).data
        response['preset'] = preset
        response['start_date'] = start
        response['end_date'] = end
        return Response(response)


class FinanceStatsView(APIView):
    """
    GET /api/stats/finance/   ?start_date=&end_date=   (patron)
    Équivalent API du tableau de bord financier.
    """
    permission_classes = [IsPatron]

    def get(self, request):
        start, end = _date_range(request, default_days=31)

        packages = PackageTable.objects.filter(created_at__date__range=[start, end])
        invoices = InvoiceTable.objects.filter(date_issued__date__range=[start, end])

        packages_by_day = (
            packages.annotate(day=TruncDate('created_at'))
            .values('day').annotate(count=Count('id')).order_by('day')
        )
        revenue_by_day = (
            invoices.annotate(day=TruncDate('date_issued'))
            .values('day').annotate(total=Sum('amount_paid')).order_by('day')
        )

        return Response({
            'start_date': start,
            'end_date': end,
            'total_packages': packages.count(),
            'total_pending': packages.filter(status='pending').count(),
            'total_in_transit': packages.filter(status='in_transit').count(),
            'total_delivered': packages.filter(status='delivered').count(),
            'total_cancelled': packages.filter(status='cancelled').count(),
            'total_revenue': money(_weighted_sum(invoices)),
            'total_paid': money(_weighted_sum(invoices.filter(paid=True))),
            'total_unpaid': money(_weighted_sum(invoices.filter(paid=False))),
            'revenue_delivered': money(_weighted_sum(invoices.filter(package__status='delivered'))),
            'cash_collected': money(invoices.aggregate(v=Sum('amount_paid'))['v'] or Decimal('0')),
            'graph_days': [str(r['day']) for r in packages_by_day],
            'graph_counts': [r['count'] for r in packages_by_day],
            'graph_revenue_days': [str(r['day']) for r in revenue_by_day],
            'graph_revenue_amounts': [float(r['total'] or 0) for r in revenue_by_day],
        })


class MeasurePriceListView(generics.ListCreateAPIView):
    """GET /api/measure-prices/ — tarifs par unité de mesure."""
    permission_classes = [ReadOnlyOrStaff]
    serializer_class = MeasurePriceSerializer
    queryset = MeasurePriceTable.objects.all()
    pagination_class = None


class ApiRootView(APIView):
    """GET /api/ — petit index, pratique pour vérifier que l'API répond."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'name': 'Lukogo Express API',
            'version': '1.0',
            'auth': {
                'login': '/api/auth/login/',
                'refresh': '/api/auth/refresh/',
                'logout': '/api/auth/logout/',
                'me': '/api/auth/me/',
            },
            'resources': {
                'manifests': '/api/manifests/',
                'packages': '/api/packages/',
                'invoices': '/api/invoices/',
                'credits': '/api/credits/',
                'payments_history': '/api/history/payments/',
                'deliveries_history': '/api/history/deliveries/',
                'dashboard': '/api/stats/dashboard/',
                'finance': '/api/stats/finance/',
            },
        })
