from django import forms
from .models import *
from django.contrib.auth.models import User
from decimal import Decimal


STATUS_CHOICES = [
    ("pending", "Attente"),
    ("in_transit", "En transit"),
    ("delivered", "Délivré"),
    ("cancelled", "Annulé"),
]


MEASURE_CHOICES = [
    ("kilo", "Kilo"),
    ("little", "Littre"),
    ("can", "Bidon"),
    ("piece", "Pièce"),
]


class ConnexionForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'placeholder':'Utilisateur ','class':'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':'Mot de passe ', 'type':'password','class':'form-control'}))



class RegistrationForm(forms.Form):
    firstname = forms.CharField( widget=forms.TextInput(attrs={'placeholder':'Nom ','class':'form-control'}), label='Nom')
    lastname = forms.CharField( widget=forms.TextInput(attrs={'placeholder':'Prénom ','class':'form-control'}), label='Prénom')
    username = forms.CharField( widget=forms.TextInput(attrs={'placeholder':'Utilisateur ','class':'form-control'}), label='Utilisateur')
    password = forms.CharField( widget=forms.PasswordInput(attrs={'placeholder':'Mot de passe ','class':'form-control'}), label='Mot de passe')
    password2 = forms.CharField( widget=forms.PasswordInput(attrs={'placeholder':'Confirmer mot de passe ','class':'form-control'}), label='Confirmer mot de passe')
    email = forms.EmailField( widget = forms.TextInput( attrs = {'placeholder':'Adresse electronique ','class':'form-control'} ), label='Adresse electronique')



class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':'Ancien mot de passe ','type':'password','class':'form-control'}))
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':'Nouveau mot de passe ', 'type':'password','class':'form-control'}))
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':'Confirmer mot de passe ', 'type':'password','class':'form-control'}))



class UserUpdateForm(forms.ModelForm):
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom'}),
        label='Prénom', required=False)
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom'}),
        label='Nom', required=False)
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
        label='Adresse e-mail')

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class ProfileForm(forms.ModelForm):
    phone = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+257 XX XXX XXX'}),
        label='Téléphone', required=False)
    address = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Adresse'}),
        label='Adresse', required=False)
    bio = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Quelques mots sur vous…', 'rows': 3}),
        label='Bio', required=False)
    avatar = forms.ImageField(
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label='Photo de profil', required=False)

    class Meta:
        model = Profile
        fields = ['phone', 'address', 'bio', 'avatar']


class PackageForm(forms.ModelForm):
    manifest = forms.ModelChoiceField(
        queryset=ManifestTable.objects.none(),  # default empty, will override below
        widget=forms.Select(attrs={
            'class': 'form-control',
            'name': 'manifest'
        }),
        label='Choisir le manifeste'
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Entrer description',
            'class': 'form-control',
            'rows': '3',
            'name': 'description'
        }),
        label='Description'
    )

    owner_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Le client',
            'class': 'form-control',
            'name': 'owner_name'
        }),
        label='Le client'
    )

    receiver_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Receveur',
            'class': 'form-control',
            'name': 'receiver_name'
        }),
        label='Receveur'
    )


    weight = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'placeholder': 'Poids',
            'class': 'form-control',
            'name': 'weight',
            'step': '0.01',
            'min': '0'
        }),
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0'),
        label='Poids'
    )

    measure = forms.ChoiceField(
        widget=forms.Select(attrs={
            'class': 'form-control',
            'name': 'measure'
        }),
        choices=MEASURE_CHOICES,
        label='Mesure'
    )

    price = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'placeholder': 'Prix par unité (USD)',
            'class': 'form-control',
            'name': 'price',
            'step': '0.01',
            'min': '0',
            'id': 'id_price',
        }),
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0'),
        label='Prix par unité (USD) '
    )

    discount = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'placeholder': '0.00',
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'id': 'id_discount',
        }),
        initial=Decimal('0'),
        min_value=Decimal('0'),
        required=False,
        label='Remise (USD)'
    )

    amount_paid = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'placeholder': '0.00',
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'id': 'id_amount_paid',
        }),
        initial=Decimal('0'),
        min_value=Decimal('0'),
        required=False,
        label='Montant payé (USD)'
    )

    class Meta:
        model = PackageTable
        fields = ['manifest', 'description', 'owner_name', 'receiver_name', 'weight', 'measure', 'price']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show manifests that are NOT full
        self.fields['manifest'].queryset = ManifestTable.objects.filter(is_full=False)
        

class ManifestForm(forms.ModelForm):
 
    vehicle_plate = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Plaque véhicule',
            'class': 'form-control',
            'name': 'vehicle_plate'
        }),
        label='Plaque véhicule'
    )

    driver_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Driver name',
            'class': 'form-control',
            'name': 'driver_name'
        }),
        label='Driver name'
    )

    departure_point = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Point de départ',
            'class': 'form-control',
            'name': 'departure_point'
        }),
        label='Point de départ'
    )

    arrival_point = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Point de arrivée',
            'class': 'form-control',
            'name': 'arrival_point'
        }),
        label='Point de arrivé'
    )

    departure_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'name': 'departure_time'
        }),
        label='Temps de départ'
    )

    arrival_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'name': 'arrival_time'
        }),
        label="Temps d'arrivée"
    )

    intermediate_stops = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Stops',
            'class': 'form-control',
            'name': 'intermediate_stops'
        }),
        label='Stops'
    )

    is_full = forms.BooleanField(
        required=False,  # allows unchecked state
        label='Complète',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'name': 'is_full',
        })
    )



    class Meta:
        model = ManifestTable
        fields = ['vehicle_plate', 'driver_name', 'departure_point', 'arrival_point', "departure_time", "arrival_time", 'intermediate_stops', 'is_full']

class UpdateManifestForm(forms.ModelForm):
 
    vehicle_plate = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Plaque véhicule',
            'class': 'form-control',
            'name': 'vehicle_plate'
        }),
        label='Plaque véhicule'
    )

    driver_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Driver name',
            'class': 'form-control',
            'name': 'driver_name'
        }),
        label='Driver name'
    )

    departure_point = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Point de départ',
            'class': 'form-control',
            'name': 'departure_point'
        }),
        label='Point de départ'
    )

    arrival_point = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Point de arrivée',
            'class': 'form-control',
            'name': 'arrival_point'
        }),
        label='Point de arrivé'
    )

    departure_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'name': 'departure_time'
        }),
        label='Temps de départ'
    )

    arrival_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'name': 'arrival_time'
        }),
        label="Temps d'arrivée"
    )

    intermediate_stops = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Stops',
            'class': 'form-control',
            'name': 'intermediate_stops'
        }),
        label='Stops'
    )



    class Meta:
        model = ManifestTable
        fields = ['vehicle_plate', 'driver_name', 'departure_point', 'arrival_point', "departure_time", "arrival_time", 'intermediate_stops']



class CompleteManifestForm(forms.ModelForm):
 
    is_full = forms.BooleanField(
        required=False,  # allows unchecked state
        label='Complète',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'name': 'is_full',
        })
    )

    class Meta:
        model = ManifestTable
        fields = ['is_full']


























