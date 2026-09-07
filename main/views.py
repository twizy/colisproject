
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import IntegrityError
from django.db.utils import IntegrityError
from .forms import *
from .models import *
from django.utils import timezone
from django.utils.timezone import make_aware
from datetime import datetime
from bs4 import BeautifulSoup
from decimal import Decimal
from django.db.models.functions import Coalesce
import json
from django.http import JsonResponse
from datetime import date, timedelta
from django.views.decorators.http import require_POST





from io import BytesIO
from django.http import FileResponse, HttpResponseForbidden
from django.contrib.auth.decorators import user_passes_test
from django.db.models.functions import TruncDate
from .finance import TOTAL_DUE, invoice_totals, total_invoiced
from django.utils import timezone
import matplotlib
matplotlib.use("Agg")   # headless backend for servers
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from openpyxl import Workbook
# Create your views here.


# ============================================================
# Helpers de rôles
#   Patron  = is_superuser
#   Staff   = is_staff (le patron est inclus partout)
#   Simple  = simplement connecté
# ============================================================
def is_patron(user):
    """Patron / propriétaire : accès total."""
    return user.is_authenticated and user.is_superuser


def is_staff_or_patron(user):
    """Staff de bureau ou patron."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def home(request):
    import calendar
    from django.db.models import Case, When, IntegerField
    # from django.core.management.utils import get_random_secret_key
    # print(get_random_secret_key())
    page_name = 'Home'
    total_manifests       = ManifestTable.objects.count()
    total_packages        = PackageTable.objects.count()
    unpaid_total_invoices = InvoiceTable.objects.filter(paid=False).count()
    total_invoices        = InvoiceTable.objects.count()
    total_users           = User.objects.count()
    delivered_packages    = PackageTable.objects.filter(status='delivered').count()
    pending_packages      = PackageTable.objects.filter(status='pending').count()
    in_transit            = PackageTable.objects.filter(status='in_transit').count()
    total_income          = InvoiceTable.objects.filter(paid=True).aggregate(Sum('amount'))['amount__sum'] or 0
    recent_manifests      = ManifestTable.objects.all()[:5]
    recent_packages       = PackageTable.objects.select_related('manifest')[:5]

    # === Chart period ===
    today      = timezone.now().date()
    month_days = calendar.monthrange(today.year, today.month)[1]   # 28/29/30/31
    preset     = request.GET.get('preset', '30d')

    if preset == '7d':
        chart_start = today - timedelta(days=6)
        chart_end   = today
    elif preset == 'month':
        chart_start = today.replace(day=1)
        chart_end   = today
    elif preset == 'custom':
        try:
            chart_start = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
        except ValueError:
            chart_start = today - timedelta(days=29)
        try:
            chart_end = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
        except ValueError:
            chart_end = today
        if chart_start > chart_end:
            chart_start, chart_end = chart_end, chart_start
    else:  # '30d' — défaut
        preset      = '30d'
        chart_start = today - timedelta(days=29)
        chart_end   = today

    nb_days  = (chart_end - chart_start).days + 1
    all_days = [chart_start + timedelta(days=i) for i in range(nb_days)]

    rows = (
        PackageTable.objects
        .filter(created_at__date__range=[chart_start, chart_end])
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            total=Count('id'),
            recuperes=Count(Case(When(status='delivered', then=1), output_field=IntegerField())),
            non_recuperes=Count(Case(When(status__in=['pending', 'in_transit'], then=1), output_field=IntegerField())),
        )
        .order_by('day')
    )
    data_map            = {row['day']: row for row in rows}
    chart_labels        = json.dumps([d.strftime('%d/%m') for d in all_days])
    chart_total         = json.dumps([data_map.get(d, {}).get('total', 0)         for d in all_days])
    chart_recuperes     = json.dumps([data_map.get(d, {}).get('recuperes', 0)     for d in all_days])
    chart_non_recuperes = json.dumps([data_map.get(d, {}).get('non_recuperes', 0) for d in all_days])

    return render(request, 'home.html', locals())


def loginView(request):
	form = ConnexionForm(request.POST)
	try:
		next_p = request.GET["next"]
	except:
		next_p = ""
	if request.method == "POST":
		if form.is_valid():
			username = form.cleaned_data['username']
			password = form.cleaned_data['password']
			user = authenticate(username=username, password=password)
			if user:
				login(request, user)
				if next_p:
					return redirect(next_p)
				else:
					return redirect(home)
			else:
				messages.error(request, "Wrong credentials!")
		else:
			html = form.errors.as_ul()
			soup = BeautifulSoup(html, "html.parser")
			
			error = soup.find("ul").find("li").find("ul").find("li").text.strip()
			messages.error(request, error)

	form = ConnexionForm()
	return render(request, 'login.html', locals())


def registerView(request):
	if request.method == "POST" :
		form = RegistrationForm(request.POST, request.FILES)
		if form.is_valid():
			username = form.cleaned_data['username']
			firstname = form.cleaned_data['firstname']
			lastname = form.cleaned_data['lastname']
			password = form.cleaned_data['password']
			password2 = form.cleaned_data['password2']
			email = form.cleaned_data['email']
			if password==password2:
				user = User.objects.create_user(
					username=username,
					email=email,
					password=password)
				user.first_name, user.last_name = firstname, lastname
				user.save()
				# messages.success(request, "Salut "+username+", vous etes enregistré avec succès!")
				if user:
					login(request, user)
					return redirect(home)
				else:
					messages.error(request, "Check internet connection!")
			else:
				messages.error(request, "Passwords don't match!")
		else:
			html = form.errors.as_ul()
			soup = BeautifulSoup(html, "html.parser")
			
			error = soup.find("ul").find("li").find("ul").find("li").text.strip()
			messages.error(request, error)

	form = RegistrationForm()
	return render(request, 'register.html', locals())


@login_required
def resetView(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            old_pw  = form.cleaned_data['old_password']
            new_pw1 = form.cleaned_data['new_password1']
            new_pw2 = form.cleaned_data['new_password2']
            if not request.user.check_password(old_pw):
                messages.error(request, 'Ancien mot de passe incorrect.')
            elif new_pw1 != new_pw2:
                messages.error(request, 'Les nouveaux mots de passe ne correspondent pas.')
            elif len(new_pw1) < 8:
                messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères.')
            else:
                request.user.set_password(new_pw1)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Mot de passe modifié avec succès !')
                return redirect('home')
    else:
        form = PasswordChangeForm()
    return render(request, 'reset.html', {'form': form})


def logoutView(request):
	logout(request)
	return redirect(home)

@login_required
def create_package(request):
    if not is_staff_or_patron(request.user):
        return redirect('home')
    form_title = "Ajouter un colis"

    if request.method == 'POST':
        form = PackageForm(request.POST)
        if form.is_valid():
            manifest      = form.cleaned_data['manifest']
            owner_name    = form.cleaned_data['owner_name']
            receiver_name = form.cleaned_data['receiver_name']
            description   = form.cleaned_data['description']
            weight        = form.cleaned_data['weight']
            measure       = form.cleaned_data['measure']
            price         = form.cleaned_data['price']
            discount      = form.cleaned_data.get('discount') or Decimal('0')
            amount_paid   = form.cleaned_data.get('amount_paid') or Decimal('0')
            created_by    = request.user

            total_due  = max(weight * price - discount, Decimal('0'))
            is_paid    = amount_paid >= total_due

            package_object = PackageTable(
                manifest=manifest, owner_name=owner_name, receiver_name=receiver_name,
                description=description, weight=weight, measure=measure,
                price=price, status='in_transit', created_by=created_by,
            )
            invoice_object = InvoiceTable(
                package=package_object, amount=price,
                discount=discount, amount_paid=amount_paid, paid=is_paid,
            )

            if package_object and invoice_object:
                package_object.save()
                invoice_object.save()
                # Historique : enregistre le versement initial s'il y en a un
                if amount_paid and amount_paid > Decimal('0'):
                    PaymentHistory.objects.create(
                        invoice=invoice_object,
                        amount=amount_paid,
                        balance_after=invoice_object.balance,
                        is_full=invoice_object.paid,
                        recorded_by=request.user,
                    )
                return redirect('home')

            else:
                html = form.errors.as_ul()
                soup = BeautifulSoup(html, "html.parser")
                
                error = soup.find("ul").find("li").find("ul").find("li").text.strip()
                error_split = error.split()[3:]
                error_message = " ".join(error_split)
                messages.error(request, error_message)

            
        else:
            html = form.errors.as_ul()
            soup = BeautifulSoup(html, "html.parser")
            
            error = soup.find("ul").find("li").find("ul").find("li").text.strip()
            error_split = error.split()[3:]
            error_message = " ".join(error_split)
            messages.error(request, error_message)
    else:
        form = PackageForm()
    return render(request, 'forms/package_form.html', locals())


@login_required
def all_packages(request):
    get_packages = PackageTable.objects.all() 
    count_packages = get_packages.count()

    return render(request, 'all_package.html', locals())


@login_required
def create_manifest(request):
    if not is_staff_or_patron(request.user):
        return redirect('home')
    form_title = "Ajouter un manifest"

    if request.method == 'POST':
        form = ManifestForm(request.POST)
        if form.is_valid():
            today = timezone.now().date()
            count_today = ManifestTable.objects.filter(created_at__date=today).count() + 1

            # Build your custom manifest code
            user = request.user
            manifest_code = f"{today.strftime('%m')}M-{today.strftime('%d%y')}-{count_today}"
            vehicle_plate = form.cleaned_data['vehicle_plate']
            driver_name = form.cleaned_data['driver_name']
            departure_point = form.cleaned_data['departure_point']
            arrival_point = form.cleaned_data['arrival_point']
            departure_time = form.cleaned_data['departure_time']
            arrival_time = form.cleaned_data['arrival_time']
            intermediate_stops = form.cleaned_data['intermediate_stops']
            created_by = request.user

            if intermediate_stops == None:
                ManifestTable(user = user, code = manifest_code, vehicle_plate = vehicle_plate, driver_name = driver_name, departure_point = departure_point, departure_time = departure_time, arrival_point = arrival_point, arrival_time = arrival_time, intermediate_stops = "Non", created_by = created_by ).save()
                return redirect('home')
            else:
                ManifestTable(user = user, code = manifest_code, vehicle_plate = vehicle_plate, driver_name = driver_name, departure_point = departure_point, departure_time = departure_time, arrival_point = arrival_point, arrival_time = arrival_time, intermediate_stops = intermediate_stops, created_by = created_by ).save()
                return redirect('home')
        else:
            html = form.errors.as_ul()
            soup = BeautifulSoup(html, "html.parser")
            
            error = soup.find("ul").find("li").find("ul").find("li").text.strip()
            error_split = error.split()[3:]
            error_message = " ".join(error_split)
            messages.error(request, error_message)
    else:
        form = ManifestForm()
    return render(request, 'forms/manifest_form.html', locals())


@login_required
def complete_manifest(request, mani_id):
    if not is_staff_or_patron(request.user):
        return redirect('home')
    form_title = "Modifier un manifest"
    get_manifet = get_object_or_404(ManifestTable, pk = mani_id)
    if request.method == 'POST':
        form = CompleteManifestForm(request.POST, instance = get_manifet)
        if form.is_valid():
            form.save()
            return redirect('home')
        else:
            html = form.errors.as_ul()
            soup = BeautifulSoup(html, "html.parser")
            
            error = soup.find("ul").find("li").text.strip()
            if error.startswith("vehicle_plate"):
                get_fields_errors = ("Plaque véhicule est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("driver_name"):
                get_fields_errors = ("Plaque véhicule est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("departure_point"):
                get_fields_errors = ("Point de départ est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("arrival_point"):
                get_fields_errors = ("Point de arrivé est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("departure_time"):
                get_fields_errors = ("Temps de départ est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("arrival_time"):
                get_fields_errors = ("Temps d'arrivée est requis !")
                messages.error(request, get_fields_errors)

            elif error.startswith("intermediate_stops"):
                get_fields_errors = ("Arret dans le chemin est requis ! Si non, ajouter Non !")
                messages.error(request, get_fields_errors)

            else:
                error_split = error.split()[0:]
                error_message = " ".join(error_split)
                messages.error(request, error_message)

    else:
        form = CompleteManifestForm(instance = get_manifet)
    return render(request, 'forms/manifest_form_complete.html', locals())


@login_required
@require_POST
def delete_manifest(request, mani_id):
    manifest = get_object_or_404(ManifestTable, pk=mani_id)
    if not is_patron(request.user):
        messages.error(request, "Permission refusée.")
        return redirect('home')
    manifest.delete()
    messages.success(request, f"Manifeste {manifest.code} supprimé.")
    return redirect('home')


@login_required
def update_manifest(request, mani_id):

    if is_staff_or_patron(request.user):
        form_title = "Modifier un manifest"
        get_manifet = get_object_or_404(ManifestTable, pk = mani_id)
        if request.method == 'POST':
            form = UpdateManifestForm(request.POST, instance = get_manifet)
            if form.is_valid():
                form.save()
                return redirect('home')
            else:
                html = form.errors.as_ul()
                soup = BeautifulSoup(html, "html.parser")
                
                error = soup.find("ul").find("li").text.strip()
                if error.startswith("vehicle_plate"):
                    get_fields_errors = ("Plaque véhicule est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("driver_name"):
                    get_fields_errors = ("Plaque véhicule est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("departure_point"):
                    get_fields_errors = ("Point de départ est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("arrival_point"):
                    get_fields_errors = ("Point de arrivé est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("departure_time"):
                    get_fields_errors = ("Temps de départ est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("arrival_time"):
                    get_fields_errors = ("Temps d'arrivée est requis !")
                    messages.error(request, get_fields_errors)

                elif error.startswith("intermediate_stops"):
                    get_fields_errors = ("Arret dans le chemin est requis ! Si non, ajouter Non !")
                    messages.error(request, get_fields_errors)

                else:
                    error_split = error.split()[0:]
                    error_message = " ".join(error_split)
                    messages.error(request, error_message)

        else:
            form = UpdateManifestForm(instance = get_manifet)

    else:
        return redirect('home')
    return render(request, 'forms/manifest_form_update.html', locals())


@login_required
def manifest_detail(request, id):
    get_id = id
    get_manifest = get_object_or_404(ManifestTable, id=id)
    get_all_packages = PackageTable.objects.filter(manifest=get_manifest).select_related('invoice')
    count_packages   = get_all_packages.count()

    total_weight  = sum(pkg.weight for pkg in get_all_packages)
    total_amount  = sum((pkg.price or 0) * (pkg.weight or 0) for pkg in get_all_packages)
    unpaid_count  = sum(1 for pkg in get_all_packages if not getattr(getattr(pkg, 'invoice', None), 'paid', True))
    # total_amount = sum(pkg.price * 2 for pkg in get_all_packages)

        # If a price per kilo exists, multiply by it
    # if get_all_packages:
    #     total_amount = Decimal(total_weight) * 200  # assuming the field is 'price'
    # else:
    #     total_amount = Decimal(0)  # fallback if no measure price found
                       
    return render(request, 'details/manifest_details.html', {
        'get_manifest':    get_manifest,
        'get_all_packages': get_all_packages,
        'count_packages':  count_packages,
        'total_weight':    total_weight,
        'total_amount':    total_amount,
        'unpaid_count':    unpaid_count,
        'get_id':          get_id,
    })

@login_required
def manifest_credits(request, mani_id):
    if not is_staff_or_patron(request.user):
        return redirect('home')
    manifest   = get_object_or_404(ManifestTable, id=mani_id)
    packages   = PackageTable.objects.filter(manifest=manifest).select_related('invoice')

    paid_list   = []
    credit_list = []

    for pkg in packages:
        invoice = getattr(pkg, 'invoice', None)
        # Mêmes définitions que la page Crédits et le tableau de bord :
        # remise déduite, acomptes comptés.
        if invoice:
            total   = invoice.total_due
            settled = invoice.amount_paid
            balance = invoice.balance
        else:
            total   = (pkg.weight or Decimal('0')) * (pkg.price or Decimal('0'))
            settled = Decimal('0')
            balance = total
        entry = {
            'pkg':     pkg,
            'invoice': invoice,
            'total':   total,
            'paid':    settled,
            'balance': balance,
        }
        if invoice and invoice.paid:
            paid_list.append(entry)
        else:
            credit_list.append(entry)

    # « Payé » = argent réellement encaissé, acomptes des colis encore en
    # crédit compris ; « crédit » = ce qui reste à percevoir.
    total_paid    = sum((e['paid'] for e in paid_list + credit_list), Decimal('0'))
    total_credit  = sum((e['balance'] for e in credit_list), Decimal('0'))
    total_global  = sum((e['total'] for e in paid_list + credit_list), Decimal('0'))
    # Total de la section « Colis payés » seule, distinct de l'encaissé global.
    paid_section_total = sum((e['total'] for e in paid_list), Decimal('0'))

    return render(request, 'details/manifest_credits.html', {
        'manifest':           manifest,
        'paid_list':          paid_list,
        'credit_list':        credit_list,
        'total_paid':         total_paid,
        'total_credit':       total_credit,
        'total_global':       total_global,
        'paid_section_total': paid_section_total,
    })


@login_required
@require_POST
def manifest_bulk_action(request, mani_id, action):
    """
    Bulk-update all packages of a manifest.
      1 → Confirmer  : in_transit + pending → delivered
      2 → En attente : in_transit           → pending
      3 → Annuler    : tout sauf delivered  → cancelled
    """
    if not is_staff_or_patron(request.user):
        messages.error(request, "Permission refusée.")
        return redirect('manifest-details', id=mani_id)

    manifest = get_object_or_404(ManifestTable, id=mani_id)
    pkgs = PackageTable.objects.filter(manifest=manifest)

    if action == 1:
        now = timezone.now()
        to_deliver = list(pkgs.filter(status__in=['in_transit', 'pending']))
        pkgs.filter(status__in=['in_transit', 'pending']).update(
            status='delivered', taken_at=now
        )
        # Historique : enregistre la récupération de chaque colis livré
        DeliveryHistory.objects.bulk_create([
            DeliveryHistory(
                package=pkg,
                received_by=pkg.receiver_name,
                recorded_by=request.user if request.user.is_authenticated else None,
                delivered_at=now,
            )
            for pkg in to_deliver
        ])
        messages.success(request, f"Manifeste {manifest.code} — tous les colis marqués comme livrés.")
    elif action == 2:
        pkgs.filter(status='in_transit').update(status='pending')
        messages.success(request, f"Manifeste {manifest.code} — colis mis en attente de récupération.")
    elif action == 3:
        pkgs.exclude(status='delivered').update(status='cancelled')
        messages.warning(request, f"Manifeste {manifest.code} — annulé.")
    else:
        messages.error(request, "Action invalide.")

    return redirect('manifest-details', id=mani_id)


# @login_required
# @csrf_exempt  # ou mieux : utiliser fetch avec le CSRF token
# def update_package_status(request, id):
#     if request.method == 'POST':
#         pkg = PackageTable.objects.filter(id=id).first()
#         if not pkg:
#             return JsonResponse({'success': False, 'message': 'Colis introuvable.'}, status=404)
        
#         pkg.status = 'delivered'
#         pkg.taken_at = timezone.now()
#         pkg.save()
#         return JsonResponse({'success': True, 'message': 'Statut mis à jour avec succès.'})
    
#     return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'}, status=405)



@login_required
@require_POST # Restricts to POST method only (cleaner than checking request.method)
def update_package_status(request, id):
    if not is_staff_or_patron(request.user):
        return JsonResponse({'success': False, 'message': 'Permission refusée.'}, status=403)
    try:
        pkg = PackageTable.objects.filter(id=id).first()
        if not pkg:
            return JsonResponse({'success': False, 'message': 'Colis introuvable.'}, status=404)

        # Parse the data sent from JavaScript
        data = json.loads(request.body)
        new_status = data.get('status')

        if new_status == 'delivered':
            pkg.status   = 'delivered'
            pkg.taken_at = timezone.now()
            # Historique : enregistre la récupération du colis
            DeliveryHistory.objects.create(
                package=pkg,
                received_by=pkg.receiver_name,
                recorded_by=request.user if request.user.is_authenticated else None,
                delivered_at=pkg.taken_at,
            )
        elif new_status == 'pending':
            pkg.status = 'pending'
        elif new_status == 'cancelled':
            pkg.status = 'cancelled'
        else:
            return JsonResponse({'success': False, 'message': 'Statut invalide.'}, status=400)

        pkg.save()
        
        # Return the new status so JS can update the text accurately
        return JsonResponse({
            'success': True, 
            'message': 'Statut mis à jour.', 
            'new_status': pkg.status
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Données invalides.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)



@login_required
@require_POST # Restricts to POST method only (cleaner than checking request.method)
def update_invoice_status(request, id):
    if not is_staff_or_patron(request.user):
        return JsonResponse({'success': False, 'message': 'Permission refusée.'}, status=403)

    try:
        invoc = InvoiceTable.objects.filter(id=id).first()
        if not invoc:
            return JsonResponse({'success': False, 'message': 'Colis introuvable.'},  status=404)

        data = json.loads(request.body)
        new_status = data.get('paid')

        if not isinstance(new_status, bool):
            return JsonResponse({'success': False, 'message': 'Statut invalide.'}, status=400)

        invoc.paid = new_status

        if new_status:
            balance_before    = invoc.balance   # solde restant avant de solder
            invoc.date_issued = timezone.now()
            invoc.amount_paid = invoc.total_due

        invoc.save()

        # Historique : enregistre le règlement du solde
        if new_status and balance_before > Decimal('0'):
            PaymentHistory.objects.create(
                invoice=invoc,
                amount=balance_before,
                balance_after=invoc.balance,
                is_full=True,
                recorded_by=request.user if request.user.is_authenticated else None,
            )

        return JsonResponse({'success': True, 'message': 'Statut mis à jour.', 'new_status': invoc.paid})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON invalide.'}, status=400)

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)



@login_required
def finance_dashboard(request):

    if not is_patron(request.user):
        return redirect('home')

    today = timezone.now().date()

    # === Date range from GET params (default: last 30 days) ===
    try:
        start_date = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
    except ValueError:
        start_date = today - timedelta(days=30)

    try:
        end_date = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
    except ValueError:
        end_date = today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    # === 1. Count by status (filtered by period) ===
    period_packages = PackageTable.objects.filter(created_at__date__range=[start_date, end_date])
    total_packages  = period_packages.count()
    total_pending   = period_packages.filter(status="pending").count()
    total_in_transit= period_packages.filter(status="in_transit").count()
    total_delivered = period_packages.filter(status="delivered").count()
    total_cancelled = period_packages.filter(status="cancelled").count()

    # === 2. Financials (filtered by period) ===
    period_invoices  = InvoiceTable.objects.filter(date_issued__date__gte=start_date, date_issued__date__lte=end_date)
    paid_invoices    = period_invoices.filter(paid=True)
    unpaid_invoices  = period_invoices.filter(paid=False)

    # Mêmes définitions que la page Crédits : le facturé déduit la remise et
    # l'encaissé compte les acomptes, y compris ceux des factures encore
    # ouvertes.
    totals = invoice_totals(period_invoices)
    total_revenue    = totals['invoiced']
    total_paid       = totals['collected']
    total_unpaid     = totals['outstanding']
    revenue_delivered= total_invoiced(period_invoices.filter(package__status="delivered"))
    revenue_period_total = total_revenue

    # === 3. Graph data by day ===
    packages_by_day = (
        period_packages
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count("id"))
        .order_by('day')
    )
    revenue_by_day = (
        period_invoices
        .annotate(day=TruncDate('date_issued'))
        .values('day')
        .annotate(total=Sum(TOTAL_DUE))
        .order_by('day')
    )

    # === 4. Serialize graph data as JSON ===
    graph_days            = json.dumps([str(d["day"]) for d in packages_by_day])
    graph_counts          = json.dumps([d["count"] for d in packages_by_day])
    graph_revenue_days    = json.dumps([str(d["day"]) for d in revenue_by_day])
    graph_revenue_amounts = json.dumps([float(d["total"]) for d in revenue_by_day])

    context = {
        "total_packages":   total_packages,
        "total_pending":    total_pending,
        "total_in_transit": total_in_transit,
        "total_delivered":  total_delivered,
        "total_cancelled":  total_cancelled,
        "total_revenue":    total_revenue,
        "total_paid":       total_paid,
        "total_unpaid":     total_unpaid,
        "revenue_delivered":     revenue_delivered,
        "revenue_last_30_days":  revenue_period_total,
        "graph_days":            graph_days,
        "graph_counts":          graph_counts,
        "graph_revenue_days":    graph_revenue_days,
        "graph_revenue_amounts": graph_revenue_amounts,
        "today":       today,
        "start_date":  start_date,
        "end_date":    end_date,
    }

    return render(request, "finance_dashboard.html", context)



@require_POST
@login_required
def record_payment(request, invoice_id):
    if not is_staff_or_patron(request.user):
        return JsonResponse({'success': False, 'message': 'Permission refusée.'}, status=403)
    try:
        invoice = get_object_or_404(InvoiceTable, id=invoice_id)
        data    = json.loads(request.body)
        payment = Decimal(str(data.get('amount', 0)))

        if payment <= 0:
            return JsonResponse({'success': False, 'message': 'Montant invalide.'}, status=400)

        current_balance = invoice.balance
        if payment > current_balance:
            payment = current_balance  # cap at remaining balance

        invoice.amount_paid += payment
        invoice.paid = invoice.amount_paid >= invoice.total_due
        invoice.save()

        # Historique : enregistre ce versement
        PaymentHistory.objects.create(
            invoice=invoice,
            amount=payment,
            balance_after=invoice.balance,
            is_full=invoice.paid,
            recorded_by=request.user if request.user.is_authenticated else None,
        )

        return JsonResponse({
            'success':     True,
            'amount_paid': float(invoice.amount_paid),
            'balance':     float(invoice.balance),
            'paid':        invoice.paid,
        })
    except (json.JSONDecodeError, Exception) as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def credits_list(request):
    if not is_staff_or_patron(request.user):
        return redirect('home')

    search = request.GET.get('q', '').strip()

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
        name = invoice.package.owner_name
        balance = invoice.balance
        if balance <= Decimal('0'):
            continue
        if name not in customers:
            customers[name] = {'invoices': [], 'total_debt': Decimal('0'), 'count': 0}
        customers[name]['invoices'].append({'invoice': invoice, 'line_total': balance})
        customers[name]['total_debt'] += balance
        customers[name]['count'] += 1

    customers_list = sorted(customers.items(), key=lambda x: x[0])
    grand_total = sum(c['total_debt'] for c in customers.values())

    return render(request, 'credits.html', {
        'customers_list': customers_list,
        'grand_total': grand_total,
        'total_customers': len(customers),
        'total_items': sum(c['count'] for c in customers.values()),
        'search': search,
    })


@login_required
def all_invoices(request):
    if not is_staff_or_patron(request.user):
        return redirect('home')

    my_invoices = (
        InvoiceTable.objects
        .select_related('package', 'package__manifest')
        .order_by('-date_issued')
    )
    all_paid_invoices   = my_invoices.filter(paid=True)
    all_unpaid_invoices = my_invoices.filter(paid=False)

    # Mêmes définitions que le tableau de bord financier et la page Crédits :
    # l'encaissé compte les acomptes, le reste dû déduit la remise.
    totals = invoice_totals(my_invoices)

    return render(request, "invoices.html", {
        'my_invoices':         my_invoices,
        'all_paid_invoices':   all_paid_invoices,
        'all_unpaid_invoices': all_unpaid_invoices,
        'total_invoiced':      totals['invoiced'],
        'total_collected':     totals['collected'],
        'total_outstanding':   totals['outstanding'],
    })


@login_required
def export_excel_backend(request):
    if not is_patron(request.user):
        return redirect('home')
    now = timezone.now()
    today = now.date()

    try:
        start_date = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
    except ValueError:
        start_date = today - timedelta(days=29)
    try:
        end_date = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
    except ValueError:
        end_date = today

    wb = Workbook()
    ws = wb.active
    ws.title = "Finance Summary"
    ws.append(['date', 'nb_packages', 'package_revenue', 'invoice_revenue'])

    nb_days = (end_date - start_date).days + 1
    for i in range(nb_days):
        day = start_date + timedelta(days=i)
        p_count = PackageTable.objects.filter(created_at__date=day).count()
        p_rev   = PackageTable.objects.filter(created_at__date=day).aggregate(total=Sum('price'))['total'] or Decimal('0.00')
        inv_rev = total_invoiced(InvoiceTable.objects.filter(date_issued__date=day))
        ws.append([day.isoformat(), p_count, float(p_rev), float(inv_rev)])

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"finance_summary_{start_date.isoformat()}_to_{end_date.isoformat()}.xlsx"
    return FileResponse(out, as_attachment=True, filename=filename)


@login_required
def export_pdf_backend(request):
    if not is_patron(request.user):
        return redirect('home')
    now = timezone.now()
    today = now.date()

    try:
        start_date = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
    except ValueError:
        start_date = today - timedelta(days=29)
    try:
        end_date = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
    except ValueError:
        end_date = today

    nb_days = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(nb_days)]
    days_str = [d.isoformat() for d in days]

    packages_series = [PackageTable.objects.filter(created_at__date=d).count() for d in days]
    invoices_series = [
        float(total_invoiced(InvoiceTable.objects.filter(date_issued__date=d)))
        for d in days
    ]

    period_invoices = InvoiceTable.objects.filter(date_issued__date__gte=start_date, date_issued__date__lte=end_date)
    period_packages = PackageTable.objects.filter(created_at__date__range=[start_date, end_date])

    img1 = BytesIO()
    fig1, ax1 = plt.subplots(figsize=(10, 3.5))
    ax1.plot(days_str, packages_series, marker='o', linewidth=1)
    ax1.set_title(f"Colis par jour ({start_date} → {end_date})")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Nb colis")
    ax1.tick_params(axis='x', rotation=45)
    fig1.tight_layout()
    fig1.savefig(img1, format='png', dpi=150)
    plt.close(fig1)
    img1.seek(0)

    img2 = BytesIO()
    fig2, ax2 = plt.subplots(figsize=(10, 3.5))
    ax2.plot(days_str, invoices_series, marker='o', linewidth=1)
    ax2.set_title(f"Revenus facturés par jour ({start_date} → {end_date})")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Montant")
    ax2.tick_params(axis='x', rotation=45)
    fig2.tight_layout()
    fig2.savefig(img2, format='png', dpi=150)
    plt.close(fig2)
    img2.seek(0)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, f"Résumé financier — {start_date} → {end_date}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 65, f"Généré le: {now.strftime('%Y-%m-%d %H:%M')}")

    kpi_y = height - 100
    line = 20   # espacement entre chaque ligne
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, kpi_y, "KPIs (période sélectionnée):")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, kpi_y - line * 1, f"Total colis : {period_packages.count()}")
    pdf.drawString(50, kpi_y - line * 2, f"Livrés : {period_packages.filter(status='delivered').count()}")
    pdf.drawString(50, kpi_y - line * 3, f"En attente : {period_packages.filter(status='pending').count()}")
    pdf.drawString(50, kpi_y - line * 4, f"En transit : {period_packages.filter(status='in_transit').count()}")
    pdf.drawString(50, kpi_y - line * 5, f"Annulés : {period_packages.filter(status='cancelled').count()}")
    period_totals = invoice_totals(period_invoices)
    pdf.drawString(50, kpi_y - line * 6, f"Total facturé : {float(period_totals['invoiced']):,.2f}")
    pdf.drawString(50, kpi_y - line * 7, f"Total encaissé : {float(period_totals['collected']):,.2f}")
    pdf.drawString(50, kpi_y - line * 8, f"Total impayé : {float(period_totals['outstanding']):,.2f}")

    img_w = width - 80
    img_h = 210
    pdf.drawImage(ImageReader(img1), 40, height - 420, width=img_w, height=img_h)
    pdf.drawImage(ImageReader(img2), 40, height - 650, width=img_w, height=img_h)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"finance_report_{start_date.isoformat()}_to_{end_date.isoformat()}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)


@login_required
def profile_view(request):
    from .models import Profile
    profile, _ = Profile.objects.get_or_create(user=request.user)

    user_form     = UserUpdateForm(instance=request.user)
    profile_form  = ProfileForm(instance=profile)
    password_form = PasswordChangeForm()

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form    = UserUpdateForm(request.POST, instance=request.user)
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Profil mis à jour avec succès.')
                return redirect('profile')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.POST)
            if password_form.is_valid():
                old_pw = password_form.cleaned_data['old_password']
                new_pw1 = password_form.cleaned_data['new_password1']
                new_pw2 = password_form.cleaned_data['new_password2']
                if not request.user.check_password(old_pw):
                    messages.error(request, 'Ancien mot de passe incorrect.')
                elif new_pw1 != new_pw2:
                    messages.error(request, 'Les nouveaux mots de passe ne correspondent pas.')
                elif len(new_pw1) < 8:
                    messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères.')
                else:
                    request.user.set_password(new_pw1)
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                    messages.success(request, 'Mot de passe changé avec succès.')
                    return redirect('profile')

    context = {
        'user_form':     user_form,
        'profile_form':  profile_form,
        'password_form': password_form,
        'packages_count':  PackageTable.objects.filter(created_by=request.user).count(),
        'manifests_count': ManifestTable.objects.filter(created_by=request.user).count(),
        'profile': profile,
    }
    return render(request, 'profile.html', context)


@login_required
def payment_history(request):
    """Historique de tous les versements (partiels et totaux) effectués sur les factures."""
    if not is_patron(request.user):
        return redirect('home')
    search = request.GET.get('q', '').strip()

    payments = (
        PaymentHistory.objects
        .select_related('invoice', 'invoice__package', 'recorded_by')
        .order_by('-created_at')
    )
    if search:
        payments = payments.filter(
            Q(invoice__package__owner_name__icontains=search) |
            Q(invoice__package__receiver_name__icontains=search) |
            Q(invoice__package__description__icontains=search)
        )

    total_amount = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    return render(request, 'history/payment_history.html', {
        'payments':     payments,
        'total_amount': total_amount,
        'count':        payments.count(),
        'search':       search,
    })


@login_required
def delivery_history(request):
    """Historique des colis récupérés : quand et par qui."""
    if not is_staff_or_patron(request.user):
        return redirect('home')
    search = request.GET.get('q', '').strip()

    deliveries = (
        DeliveryHistory.objects
        .select_related('package', 'package__manifest', 'recorded_by')
        .order_by('-delivered_at')
    )
    if search:
        deliveries = deliveries.filter(
            Q(received_by__icontains=search) |
            Q(package__owner_name__icontains=search) |
            Q(package__description__icontains=search)
        )

    return render(request, 'history/delivery_history.html', {
        'deliveries': deliveries,
        'count':      deliveries.count(),
        'search':     search,
    })


@login_required
@require_POST
def edit_delivery_receiver(request, delivery_id):
    """Modifie le nom du receveur (celui qui a récupéré le colis) d'une ligne d'historique."""
    if not is_staff_or_patron(request.user):
        return JsonResponse({'success': False, 'message': 'Permission refusée.'}, status=403)
    try:
        delivery = get_object_or_404(DeliveryHistory, id=delivery_id)
        data     = json.loads(request.body)
        new_name = (data.get('received_by') or '').strip()

        if not new_name:
            return JsonResponse({'success': False, 'message': 'Le nom du receveur est requis.'}, status=400)

        delivery.received_by = new_name
        delivery.save()

        return JsonResponse({'success': True, 'received_by': delivery.received_by})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Données invalides.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)




























