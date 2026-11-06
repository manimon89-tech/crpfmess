from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views
urlpatterns = [
 path("select-mess/<int:mess_id>/", login_required(views.select_mess), name="select_mess"),
 path("", login_required(views.dashboard), name="dashboard"), path("settings/", login_required(views.settings_view), name="settings"),
 path("members/", login_required(views.members), name="members"),
 path("members/add/", login_required(views.member_add), name="member_add"),
 path("members/import-excel/", login_required(views.member_import_excel), name="member_import_excel"),
 path("members/template.xlsx", login_required(views.member_excel_template), name="member_excel_template"),
 path("stock/", login_required(views.stock), name="stock"), path("stock/print/", login_required(views.stock_print), name="stock_print"), path("stock/audit/", login_required(views.stock_audit), name="stock_audit"),
 path("stock/add/", login_required(views.stock_add), name="stock_add"), path("stock/add-quantity/", login_required(views.stock_add_quantity), name="stock_add_quantity"),
 path("purchases/", login_required(views.purchases), name="purchases"), path("purchases/add/", login_required(views.purchase_add), name="purchase_add"),
 path("consumption/", login_required(views.consumption), name="consumption"), path("consumption/add/", login_required(views.consumption_add), name="consumption_add"),
 path("sold-ration/", login_required(views.sold_ration), name="sold_ration"), path("sold-ration/add/", login_required(views.sold_ration_add), name="sold_ration_add"),
 path("attendance/", login_required(views.attendance), name="attendance"), path("payments/", login_required(views.payments), name="payments"), path("payments/add/", login_required(views.payment_add), name="payment_add"),
 path("summary/", login_required(views.monthly_summary), name="monthly_summary"), path("summary/print/", login_required(views.print_charges), name="print_charges"),
]
