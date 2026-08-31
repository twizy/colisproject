from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal

# Create your models here.


# class User(AbstractUser):
#     email               = models.EmailField(unique = True)
#     is_admin            = models.BooleanField(default = False)
#     is_user             = models.BooleanField(default = True)
#     groups              = models.ManyToManyField(Group, 
#                         related_name = "custom_user_set", 
#                         blank = True, 
#                         help_text   = "The groups this user belongs to.", 
#                         verbose_name = "groups")
#     user_permissions    = models.ManyToManyField(Permission, 
#                         related_name = "custom_user_permissions_set", 
#                         blank = True, 
#                         help_text   = "Specific permission for this user.", 
#                         verbose_name = "user permissions")

#     def __str__(self):
#         return self.username

#     class Meta:
#         ordering = ['username']



class ManifestTable(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user')
    code = models.CharField(max_length=100, unique=True)
    vehicle_plate = models.CharField(max_length=20)
    driver_name = models.CharField(max_length=100)
    departure_point = models.CharField(max_length=100)
    arrival_point = models.CharField(max_length=100)
    intermediate_stops = models.TextField(blank=True, null=True, default="Non")
    departure_time = models.TimeField()
    arrival_time = models.TimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_manifests')
    created_at = models.DateTimeField(auto_now_add=True)
    is_full = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.vehicle_plate} - {self.departure_point} → {self.arrival_point}"

    class Meta:
        ordering = ['-created_at']


class MeasurePriceTable(models.Model):
    measure = models.CharField(
        max_length=20,
        choices=[
            ('kilo', 'Kilo'),
            ('little', 'Littre'),
            ('can', 'Bidon'),
            ('piece', 'Pièce')
        ],
        default='kilo'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.price} for {self.measure}"
    

class PackageTable(models.Model):
    manifest = models.ForeignKey(ManifestTable, on_delete=models.CASCADE, related_name='packages')
    owner_name = models.CharField(max_length=100)
    receiver_name = models.CharField(max_length=100)
    description = models.TextField()
    weight = models.DecimalField(max_digits=10, decimal_places=2)
    measure = models.CharField(
        max_length=20,
        choices=[
            ('kilo', 'Kilo'),
            ('little', 'Littre'),
            ('can', 'Bidon'),
            ('piece', 'Pièce')
        ],
        default='kilo'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Attente'),
            ('in_transit', 'En transit'),
            ('delivered', 'Délivré'),
            ('cancelled', 'Annulé')
        ],
        default='pending'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='packages_created')
    created_at = models.DateTimeField(auto_now_add=True)
    taken_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Package #{self.id} - {self.description} de {self.owner_name} | {self.created_at}"

    class Meta:
        ordering = ['-created_at']


class InvoiceTable(models.Model):
    package = models.OneToOneField(PackageTable, on_delete=models.CASCADE, related_name='invoice')
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # price per unit
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    date_issued = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)

    def __str__(self):
        return f"Invoice for Package {self.package.id}"

    @property
    def total_due(self):
        return max(self.package.weight * self.amount - self.discount, Decimal('0'))

    @property
    def balance(self):
        return max(self.total_due - self.amount_paid, Decimal('0'))

    def mark_as_paid(self):
        self.paid = True
        self.amount_paid = self.total_due
        self.save()


class Profile(models.Model):
    user    = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone   = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    address = models.CharField(max_length=200, blank=True, verbose_name='Adresse')
    avatar  = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Photo de profil')
    bio     = models.TextField(blank=True, verbose_name='Bio')

    def __str__(self):
        return f"Profil de {self.user.username}"


class ReportTable(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    title = models.CharField(max_length=255)
    content = models.TextField()
    client_email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report: {self.title} by {self.user.username}"

    def send_to_client(self):
        # Example email sending function
        send_mail(
            subject=f"Report: {self.title}",
            message=self.content,
            from_email='noreply@yourapp.com',
            recipient_list=[self.client_email],
        )


class PaymentHistory(models.Model):
    """Trace chaque versement d'une facture (partiel ou total) jusqu'au solde."""
    invoice        = models.ForeignKey(InvoiceTable, on_delete=models.CASCADE, related_name='payments')
    amount         = models.DecimalField(max_digits=10, decimal_places=2)            # montant de ce versement
    balance_after  = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))  # solde restant après
    is_full        = models.BooleanField(default=False)                              # True si ce versement a soldé la facture
    recorded_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_recorded')
    created_at     = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Paiement {self.amount} sur facture #{self.invoice_id} le {self.created_at:%d/%m/%Y}"

    class Meta:
        ordering = ['-created_at']


class DeliveryHistory(models.Model):
    """Trace la récupération/livraison d'un colis : quand et par qui."""
    package      = models.ForeignKey(PackageTable, on_delete=models.CASCADE, related_name='deliveries')
    received_by  = models.CharField(max_length=100, blank=True)   # celui qui a récupéré le colis (receveur)
    recorded_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries_recorded')  # agent ayant enregistré
    delivered_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Colis #{self.package_id} livré le {self.delivered_at:%d/%m/%Y}"

    class Meta:
        ordering = ['-delivered_at']



