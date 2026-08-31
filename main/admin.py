from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(ManifestTable)
admin.site.register(PackageTable)
admin.site.register(InvoiceTable)
admin.site.register(MeasurePriceTable)
admin.site.register(ReportTable)


