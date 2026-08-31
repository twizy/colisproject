"""
Routes de l'API — préfixées par /api/ (voir colisproject/urls.py).

    POST   /api/auth/login/                     obtention access + refresh + user
    POST   /api/auth/refresh/                   nouveau access (rotation activée)
    POST   /api/auth/verify/                    validité d'un token
    POST   /api/auth/register/
    POST   /api/auth/logout/                    blacklist du refresh
    GET    /api/auth/me/            PATCH
    POST   /api/auth/change-password/

    GET    /api/manifests/          POST
    GET    /api/manifests/<id>/     PATCH  DELETE
    GET    /api/manifests/<id>/packages/
    GET    /api/manifests/<id>/credits/
    POST   /api/manifests/<id>/bulk-action/
    POST   /api/manifests/<id>/complete/

    GET    /api/packages/           POST
    GET    /api/packages/<id>/      PATCH  DELETE
    POST   /api/packages/<id>/status/

    GET    /api/invoices/
    GET    /api/invoices/<id>/      PATCH
    POST   /api/invoices/<id>/pay/
    POST   /api/invoices/<id>/status/
    GET    /api/credits/

    GET    /api/history/payments/
    GET    /api/history/deliveries/
    PATCH  /api/history/deliveries/<id>/

    GET    /api/stats/dashboard/
    GET    /api/stats/finance/
    GET    /api/measure-prices/
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from . import views

app_name = 'api'

urlpatterns = [
    path('', views.ApiRootView.as_view(), name='root'),

    # --- Authentification ---
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='token-verify'),
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/me/', views.MeView.as_view(), name='me'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='change-password'),

    # --- Manifestes ---
    path('manifests/', views.ManifestListCreateView.as_view(), name='manifest-list'),
    path('manifests/<int:pk>/', views.ManifestDetailView.as_view(), name='manifest-detail'),
    path('manifests/<int:pk>/packages/', views.ManifestPackagesView.as_view(), name='manifest-packages'),
    path('manifests/<int:pk>/credits/', views.ManifestCreditsView.as_view(), name='manifest-credits'),
    path('manifests/<int:pk>/bulk-action/', views.ManifestBulkActionView.as_view(), name='manifest-bulk-action'),
    path('manifests/<int:pk>/complete/', views.ManifestCompleteView.as_view(), name='manifest-complete'),

    # --- Colis ---
    path('packages/', views.PackageListCreateView.as_view(), name='package-list'),
    path('packages/<int:pk>/', views.PackageDetailView.as_view(), name='package-detail'),
    path('packages/<int:pk>/status/', views.PackageStatusView.as_view(), name='package-status'),

    # --- Factures ---
    path('invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/pay/', views.InvoicePayView.as_view(), name='invoice-pay'),
    path('invoices/<int:pk>/status/', views.InvoiceStatusView.as_view(), name='invoice-status'),
    path('credits/', views.CreditsView.as_view(), name='credits'),

    # --- Historiques ---
    path('history/payments/', views.PaymentHistoryListView.as_view(), name='payment-history'),
    path('history/deliveries/', views.DeliveryHistoryListView.as_view(), name='delivery-history'),
    path('history/deliveries/<int:pk>/', views.DeliveryHistoryUpdateView.as_view(), name='delivery-history-update'),

    # --- Statistiques ---
    path('stats/dashboard/', views.DashboardStatsView.as_view(), name='stats-dashboard'),
    path('stats/finance/', views.FinanceStatsView.as_view(), name='stats-finance'),

    # --- Référentiel ---
    path('measure-prices/', views.MeasurePriceListView.as_view(), name='measure-prices'),
]
