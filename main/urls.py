from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from .views import *

urlpatterns = [
    path('', home, name='home'),
    path('login/', loginView, name='login'),
    path('register/', registerView, name='register'),
    path('reset/', resetView, name="reset"),
    path('logout/', logoutView, name="logout"),
    path('package/', create_package, name='package'),
    path('manifest/', create_manifest, name='manifest'),

    path('manifest-details/<int:id>/', manifest_detail, name='manifest-details'),
    path('manifest-credits/<int:mani_id>/', manifest_credits, name='manifest-credits'),
    path('update-package-status/<int:id>/', update_package_status, name='update-package-status'),
    path('update-invoice-status/<int:id>/', update_invoice_status, name='update-invoice-status'),

    path('manifest-action/<int:mani_id>/<int:action>/', manifest_bulk_action, name='manifest-action'),
    path('update-manifest/<int:mani_id>/', update_manifest, name='update-manifest'),
    path('complete-manifest/<int:mani_id>/', complete_manifest, name='complete-manifest'),
    path('delete-manifest/<int:mani_id>/', delete_manifest, name='delete-manifest'),
    path('invoices/', all_invoices, name='invoices'),
    path('credits/', credits_list, name='credits'),
    path('record-payment/<int:invoice_id>/', record_payment, name='record-payment'),

    path('all-package/', all_packages, name='all-package'),

    path('payment-history/', payment_history, name='payment-history'),
    path('delivery-history/', delivery_history, name='delivery-history'),
    path('delivery-history/<int:delivery_id>/edit-receiver/', edit_delivery_receiver, name='edit-delivery-receiver'),

    path('profile/', profile_view, name='profile'),
    path('finance/', finance_dashboard, name='finance'),
    path('export/excel/', export_excel_backend, name='export_excel_backend'),
    path('export/pdf/', export_pdf_backend, name='export_pdf_backend'),

    
]