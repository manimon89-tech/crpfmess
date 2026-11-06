from django import forms
from .models import MessSetting, Member, StockItem, Purchase, StockAddition, Consumption, Payment, SoldRation
class StyledModelForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-control")
class SettingForm(StyledModelForm):
    class Meta: model=MessSetting; fields=["full_daily_charge"]
class MemberForm(StyledModelForm):
    class Meta: model=Member; fields=["member_no","name","designation","active","joined_on"]
class StockItemForm(StyledModelForm):
    class Meta: model=StockItem; fields=["name","unit","quantity","average_unit_cost","reorder_level"]
class PurchaseForm(StyledModelForm):
    class Meta: model=Purchase; fields=["date","amount","supplier_name","bill_pdf","notes"]
    widgets={"date":forms.DateInput(attrs={"type":"date"})}
class StockAdditionForm(StyledModelForm):
    class Meta: model=StockAddition; fields=["date","item","quantity","unit_cost","notes"]
    widgets={"date":forms.DateInput(attrs={"type":"date"})}
class ConsumptionForm(StyledModelForm):
    class Meta: model=Consumption; fields=["date","item","quantity","remarks"]
    widgets={"date":forms.DateInput(attrs={"type":"date"})}
class PaymentForm(StyledModelForm):
    class Meta: model=Payment; fields=["date","member","amount","reference","remarks"]
    widgets={"date":forms.DateInput(attrs={"type":"date"})}


class SoldRationForm(StyledModelForm):
    class Meta:
        model = SoldRation
        fields = ["date", "item", "quantity", "name"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
