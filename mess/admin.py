from django.contrib import admin
from .models import (
    Mess, UserMessAccess, MessSetting, Member, StockItem, Purchase,
    StockAddition, Consumption, Attendance, Payment, SoldRation
)

@admin.register(Mess)
class MessAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")

@admin.register(UserMessAccess)
class UserMessAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "mess")
    list_filter = ("role", "mess")
    search_fields = ("user__username", "mess__name")
    autocomplete_fields = ("user", "mess")

admin.site.register(MessSetting)
@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("member_no", "name", "mess", "designation", "active", "joined_on")
    list_filter = ("mess", "active")
    search_fields = ("member_no", "name")

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "mess", "unit", "quantity", "average_unit_cost", "reorder_level")
    list_filter = ("mess",)

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("date", "mess", "supplier_name", "amount")
    list_filter = ("mess", "date")

@admin.register(StockAddition)
class StockAdditionAdmin(admin.ModelAdmin):
    list_display = ("date", "mess", "item", "quantity", "unit_cost")
    list_filter = ("mess", "date", "item")

@admin.register(Consumption)
class ConsumptionAdmin(admin.ModelAdmin):
    list_display = ("date", "mess", "item", "quantity", "unit_cost_at_issue")
    list_filter = ("mess", "date")

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "mess", "member", "status", "daily_charge")
    list_filter = ("mess", "date", "status")

admin.site.register(Payment)
admin.site.register(SoldRation)
