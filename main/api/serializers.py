"""
Serializers de l'API Lukogo Express.

Les serializers de création reproduisent la logique métier des vues web
(main/views.py) : génération du code manifeste, création automatique de la
facture avec le colis, écriture de l'historique des paiements, etc.
"""
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from ..models import (
    ManifestTable,
    PackageTable,
    InvoiceTable,
    MeasurePriceTable,
    Profile,
    PaymentHistory,
    DeliveryHistory,
)


def money(value):
    """
    Montant en chaîne à 2 décimales.

    DRF sérialise déjà les DecimalField en chaîne ; on applique la même règle
    aux champs calculés pour que le client Android n'ait qu'un seul type à
    gérer pour l'argent (jamais un float, jamais d'arrondi surprise).
    """
    return f"{Decimal(value or 0):.2f}"


# ============================================================
# Utilisateur / profil
# ============================================================

class ProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['phone', 'address', 'bio', 'avatar', 'avatar_url']
        extra_kwargs = {'avatar': {'write_only': True, 'required': False}}

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get('request')
        url = obj.avatar.url
        return request.build_absolute_uri(url) if request else url


class UserSerializer(serializers.ModelSerializer):
    """Utilisateur + profil + rôle calculé, tel que consommé par Android."""
    profile = ProfileSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'is_staff', 'is_superuser', 'role', 'date_joined', 'last_login',
            'profile',
        ]
        read_only_fields = ['id', 'is_staff', 'is_superuser', 'date_joined', 'last_login']

    def get_role(self, obj):
        if obj.is_superuser:
            return 'patron'
        if obj.is_staff:
            return 'staff'
        return 'user'

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class UserUpdateSerializer(serializers.ModelSerializer):
    """Mise à jour de son propre compte + profil imbriqué (PATCH /api/auth/me/)."""
    profile = ProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'profile']

    def validate_email(self, value):
        if value and User.objects.exclude(pk=self.instance.pk).filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data is not None:
            profile, _ = Profile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password2']

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': "Les mots de passe ne correspondent pas."})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        Profile.objects.get_or_create(user=user)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password1 = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Ancien mot de passe incorrect.")
        return value

    def validate(self, attrs):
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError(
                {'new_password2': "Les nouveaux mots de passe ne correspondent pas."}
            )
        validate_password(attrs['new_password1'], self.context['request'].user)
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password1'])
        user.save()
        return user


# ============================================================
# JWT
# ============================================================

class LukogoTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    POST /api/auth/login/  ->  {"access", "refresh", "user": {...}}

    Le rôle est aussi embarqué dans les claims du token pour qu'Android puisse
    afficher/masquer des écrans sans requête supplémentaire.
    """
    default_error_messages = {
        'no_active_account': "Nom d'utilisateur ou mot de passe incorrect."
    }

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        token['role'] = 'patron' if user.is_superuser else ('staff' if user.is_staff else 'user')
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user, context=self.context).data
        return data


# ============================================================
# Tarifs
# ============================================================

class MeasurePriceSerializer(serializers.ModelSerializer):
    measure_display = serializers.CharField(source='get_measure_display', read_only=True)

    class Meta:
        model = MeasurePriceTable
        fields = ['id', 'measure', 'measure_display', 'price']


# ============================================================
# Factures
# ============================================================

class InvoiceSerializer(serializers.ModelSerializer):
    total_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    package_id = serializers.IntegerField(source='package.id', read_only=True)
    owner_name = serializers.CharField(source='package.owner_name', read_only=True)
    receiver_name = serializers.CharField(source='package.receiver_name', read_only=True)
    description = serializers.CharField(source='package.description', read_only=True)
    manifest_code = serializers.CharField(source='package.manifest.code', read_only=True)

    class Meta:
        model = InvoiceTable
        fields = [
            'id', 'package_id', 'manifest_code', 'owner_name', 'receiver_name', 'description',
            'amount', 'discount', 'amount_paid', 'total_due', 'balance',
            'paid', 'date_issued',
        ]
        read_only_fields = ['id', 'date_issued']


class InvoiceMiniSerializer(serializers.ModelSerializer):
    """Version compacte imbriquée dans un colis."""
    total_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceTable
        fields = ['id', 'amount', 'discount', 'amount_paid', 'total_due', 'balance', 'paid', 'date_issued']


class RecordPaymentSerializer(serializers.Serializer):
    """POST /api/invoices/<id>/pay/ — versement partiel ou total."""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))


class InvoicePaidStatusSerializer(serializers.Serializer):
    """POST /api/invoices/<id>/status/ — bascule payé / impayé."""
    paid = serializers.BooleanField()


# ============================================================
# Colis
# ============================================================

class PackageSerializer(serializers.ModelSerializer):
    invoice = InvoiceMiniSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    measure_display = serializers.CharField(source='get_measure_display', read_only=True)
    manifest_code = serializers.CharField(source='manifest.code', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, default=None)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = PackageTable
        fields = [
            'id', 'manifest', 'manifest_code', 'owner_name', 'receiver_name', 'description',
            'weight', 'measure', 'measure_display', 'price', 'total_amount',
            'status', 'status_display', 'created_by', 'created_by_username',
            'created_at', 'taken_at', 'invoice',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']

    def get_total_amount(self, obj):
        return money((obj.weight or Decimal('0')) * (obj.price or Decimal('0')))


class PackageCreateSerializer(serializers.ModelSerializer):
    """
    Création d'un colis — reproduit main.views.create_package :
    le colis part en 'in_transit', la facture est créée dans la foulée et
    le versement initial (s'il existe) est tracé dans PaymentHistory.
    """
    discount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal('0'), write_only=True
    )
    amount_paid = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal('0'), write_only=True
    )

    class Meta:
        model = PackageTable
        fields = [
            'manifest', 'owner_name', 'receiver_name', 'description',
            'weight', 'measure', 'price', 'discount', 'amount_paid',
        ]

    def validate_weight(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le poids doit être supérieur à zéro.")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix ne peut pas être négatif.")
        return value

    def validate_manifest(self, value):
        if value.is_full:
            raise serializers.ValidationError("Ce manifeste est clôturé, impossible d'y ajouter un colis.")
        return value

    def validate(self, attrs):
        discount = attrs.get('discount') or Decimal('0')
        if discount < 0:
            raise serializers.ValidationError({'discount': "La remise ne peut pas être négative."})
        if (attrs.get('amount_paid') or Decimal('0')) < 0:
            raise serializers.ValidationError({'amount_paid': "Le montant payé ne peut pas être négatif."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        discount = validated_data.pop('discount', None) or Decimal('0')
        amount_paid = validated_data.pop('amount_paid', None) or Decimal('0')
        user = self.context['request'].user

        package = PackageTable.objects.create(
            status='in_transit',
            created_by=user,
            **validated_data,
        )

        total_due = max(package.weight * package.price - discount, Decimal('0'))
        invoice = InvoiceTable.objects.create(
            package=package,
            amount=package.price,
            discount=discount,
            amount_paid=amount_paid,
            paid=amount_paid >= total_due,
        )

        if amount_paid > Decimal('0'):
            PaymentHistory.objects.create(
                invoice=invoice,
                amount=amount_paid,
                balance_after=invoice.balance,
                is_full=invoice.paid,
                recorded_by=user,
            )
        return package

    def to_representation(self, instance):
        return PackageSerializer(instance, context=self.context).data


class PackageStatusSerializer(serializers.Serializer):
    """POST /api/packages/<id>/status/"""
    status = serializers.ChoiceField(choices=['pending', 'in_transit', 'delivered', 'cancelled'])
    received_by = serializers.CharField(required=False, allow_blank=True)


# ============================================================
# Manifestes
# ============================================================

class ManifestSerializer(serializers.ModelSerializer):
    packages_count = serializers.SerializerMethodField()
    total_weight = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    unpaid_count = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ManifestTable
        fields = [
            'id', 'code', 'vehicle_plate', 'driver_name',
            'departure_point', 'arrival_point', 'intermediate_stops',
            'departure_time', 'arrival_time', 'is_full',
            'created_by', 'created_by_username', 'created_at',
            'packages_count', 'total_weight', 'total_amount', 'unpaid_count',
        ]
        read_only_fields = ['id', 'code', 'created_by', 'created_at']

    def _packages(self, obj):
        return obj.packages.all()

    def get_packages_count(self, obj):
        # Les vues de liste annotent packages_count (une seule requête) ; après
        # une création ou une action groupée l'objet n'est pas annoté, on
        # retombe alors sur les colis déjà préchargés. Le champ est ainsi
        # toujours présent dans la réponse, ce dont dépend le client Android.
        annotated = getattr(obj, 'packages_count', None)
        if annotated is not None:
            return annotated
        return len(self._packages(obj))

    def get_total_weight(self, obj):
        return money(sum((p.weight or Decimal('0')) for p in self._packages(obj)))

    def get_total_amount(self, obj):
        return money(sum((p.weight or Decimal('0')) * (p.price or Decimal('0')) for p in self._packages(obj)))

    def get_unpaid_count(self, obj):
        return sum(
            1 for p in self._packages(obj)
            if not getattr(getattr(p, 'invoice', None), 'paid', True)
        )


class ManifestDetailSerializer(ManifestSerializer):
    """Manifeste + ses colis, pour l'écran détail Android."""
    packages = PackageSerializer(many=True, read_only=True)

    class Meta(ManifestSerializer.Meta):
        fields = ManifestSerializer.Meta.fields + ['packages']


class ManifestCreateSerializer(serializers.ModelSerializer):
    """
    Création d'un manifeste — le code est généré côté serveur, comme dans
    main.views.create_manifest : MM'M'-JJAA-<n° du jour>.
    """
    class Meta:
        model = ManifestTable
        fields = [
            'vehicle_plate', 'driver_name', 'departure_point', 'arrival_point',
            'intermediate_stops', 'departure_time', 'arrival_time',
        ]

    def validate(self, attrs):
        if attrs.get('departure_point') and attrs.get('arrival_point'):
            if attrs['departure_point'].strip().lower() == attrs['arrival_point'].strip().lower():
                raise serializers.ValidationError(
                    {'arrival_point': "Le point d'arrivée doit être différent du point de départ."}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        today = timezone.now().date()

        # Code unique : on repart du compteur du jour et on incrémente tant
        # qu'une collision existe (deux agents peuvent créer en parallèle).
        count_today = ManifestTable.objects.filter(created_at__date=today).count() + 1
        while True:
            code = f"{today.strftime('%m')}M-{today.strftime('%d%y')}-{count_today}"
            if not ManifestTable.objects.filter(code=code).exists():
                break
            count_today += 1

        if not validated_data.get('intermediate_stops'):
            validated_data['intermediate_stops'] = "Non"

        return ManifestTable.objects.create(
            user=user,
            created_by=user,
            code=code,
            **validated_data,
        )

    def to_representation(self, instance):
        return ManifestSerializer(instance, context=self.context).data


class ManifestBulkActionSerializer(serializers.Serializer):
    """
    POST /api/manifests/<id>/bulk-action/
      1 -> Confirmer  : in_transit + pending -> delivered
      2 -> En attente : in_transit           -> pending
      3 -> Annuler    : tout sauf delivered  -> cancelled
    """
    action = serializers.ChoiceField(choices=[1, 2, 3])


# ============================================================
# Historiques
# ============================================================

class PaymentHistorySerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='invoice.package.owner_name', read_only=True)
    receiver_name = serializers.CharField(source='invoice.package.receiver_name', read_only=True)
    description = serializers.CharField(source='invoice.package.description', read_only=True)
    package_id = serializers.IntegerField(source='invoice.package.id', read_only=True)
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)

    class Meta:
        model = PaymentHistory
        fields = [
            'id', 'invoice', 'package_id', 'owner_name', 'receiver_name', 'description',
            'amount', 'balance_after', 'is_full',
            'recorded_by', 'recorded_by_username', 'created_at',
        ]


class DeliveryHistorySerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='package.owner_name', read_only=True)
    description = serializers.CharField(source='package.description', read_only=True)
    manifest_code = serializers.CharField(source='package.manifest.code', read_only=True)
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)

    class Meta:
        model = DeliveryHistory
        fields = [
            'id', 'package', 'manifest_code', 'owner_name', 'description',
            'received_by', 'recorded_by', 'recorded_by_username', 'delivered_at',
        ]
        read_only_fields = ['id', 'package', 'recorded_by', 'delivered_at']

    def validate_received_by(self, value):
        if not (value or '').strip():
            raise serializers.ValidationError("Le nom du receveur est requis.")
        return value.strip()


# ============================================================
# Tableaux de bord (lecture seule, structures calculées)
# ============================================================

class DashboardStatsSerializer(serializers.Serializer):
    total_manifests = serializers.IntegerField()
    total_packages = serializers.IntegerField()
    total_users = serializers.IntegerField()
    total_invoices = serializers.IntegerField()
    unpaid_invoices = serializers.IntegerField()
    delivered_packages = serializers.IntegerField()
    pending_packages = serializers.IntegerField()
    in_transit_packages = serializers.IntegerField()
    cancelled_packages = serializers.IntegerField()
    total_income = serializers.DecimalField(max_digits=14, decimal_places=2)
    chart_labels = serializers.ListField(child=serializers.CharField())
    chart_total = serializers.ListField(child=serializers.IntegerField())
    chart_delivered = serializers.ListField(child=serializers.IntegerField())
    chart_not_delivered = serializers.ListField(child=serializers.IntegerField())


class CreditCustomerSerializer(serializers.Serializer):
    """Un client débiteur et le détail de ses factures impayées."""
    owner_name = serializers.CharField()
    total_debt = serializers.DecimalField(max_digits=14, decimal_places=2)
    count = serializers.IntegerField()
    invoices = InvoiceSerializer(many=True)
