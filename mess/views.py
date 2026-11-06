from datetime import date, timedelta
from decimal import Decimal
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.storage import default_storage
from io import BytesIO
from openpyxl import load_workbook, Workbook
from django.utils import timezone
from .models import Mess, MessSetting, Member, StockItem, Purchase, StockAddition, Consumption, Attendance, Payment, SoldRation
from .forms import SettingForm, MemberForm, StockItemForm, PurchaseForm, StockAdditionForm, ConsumptionForm, PaymentForm, SoldRationForm

def cycle_dates(value):
    """Mess cycle: 26th through 25th. Returns (start, end), inclusive."""
    if value.day >= 26:
        start = value.replace(day=26)
        next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month.replace(day=25)
    else:
        prev_month_last = value.replace(day=1) - timedelta(days=1)
        start = prev_month_last.replace(day=26)
        end = value.replace(day=25)
    return start, end

def select_mess(request, mess_id=None):
    """Superuser selects the working mess for data entry; CO cannot switch scope."""
    if not request.user.is_superuser:
        return HttpResponse("Only the Superuser can switch the working mess.", status=403)
    if request.method != "POST":
        return redirect("dashboard")
    mess = Mess.objects.filter(pk=mess_id, is_active=True).first()
    if not mess:
        messages.error(request, "The selected mess is unavailable.")
        return redirect("dashboard")
    request.session["active_mess_id"] = mess.pk
    messages.success(request, f"Working mess changed to {mess.name}.")
    return redirect("dashboard")

def dashboard(request):
    today = timezone.localdate()
    start, end = cycle_dates(today)
    if request.mess_role == "CO":
        mess_cards = []
        for mess in request.accessible_messes:
            members_qs = Member.objects.filter(mess=mess, active=True)
            stock_qs = StockItem.objects.filter(mess=mess)
            consumption_qs = Consumption.objects.filter(mess=mess, date=today)
            attendance_qs = Attendance.objects.filter(mess=mess, date=today).select_related("member")
            sold_qs = SoldRation.objects.filter(mess=mess, date=today)
            consumed = sum((c.total_cost for c in consumption_qs), Decimal("0"))
            income = sum((a.charge for a in attendance_qs), Decimal("0")) + sum((r.total_amount for r in sold_qs), Decimal("0"))
            mess_cards.append({
                "mess": mess,
                "members": members_qs.count(),
                "stock_value": sum((i.stock_value for i in stock_qs), Decimal("0")),
                "consumed_cost": consumed,
                "daily_income": income,
                "daily_result": income-consumed,
                "low_stock": stock_qs.filter(quantity__lte=0).count(),
            })
        return render(request, "mess/co_dashboard.html", {"today": today, "start": start, "end": end, "mess_cards": mess_cards})
    setting = MessSetting.current()
    consumed_cost = sum((c.total_cost for c in Consumption.objects.filter(date=today)), Decimal("0"))
    daily_income = sum((a.charge for a in Attendance.objects.filter(date=today).select_related("member")), Decimal("0"))
    sold_today = sum((r.total_amount for r in SoldRation.objects.filter(date=today)), Decimal("0"))
    daily_income += sold_today
    return render(request, "mess/dashboard.html", {
        "today": today, "start": start, "end": end, "setting": setting,
        "members": Member.objects.filter(active=True).count(),
        "stock_value": sum((i.stock_value for i in StockItem.objects.all()), Decimal("0")),
        "consumed_cost": consumed_cost, "daily_income": daily_income,
        "daily_result": daily_income-consumed_cost,
        "low_stock": StockItem.objects.filter(quantity__lte=0),
    })

def settings_view(request):
    obj=MessSetting.current(); form=SettingForm(request.POST or None,instance=obj)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Daily charge updated."); return redirect("dashboard")
    return render(request,"mess/form.html",{"form":form,"title":"Mess settings / daily charge"})

def members(request):
    return render(request, "mess/members.html", {"members": Member.objects.all()})

def member_excel_template(request):
    """Download a ready-to-fill Excel template for bulk member entry."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    ws.append(["member_no", "name", "designation", "active", "joined_on"])
    ws.append(["M001", "Sample Member", "Dining Member", "Yes", timezone.localdate().isoformat()])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, width in {"A": 18, "B": 28, "C": 24, "D": 12, "E": 16}.items():
        ws.column_dimensions[col].width = width
    output = BytesIO()
    wb.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="mess_members_template.xlsx"'
    return response

def member_import_excel(request):
    if request.method != "POST" or not request.FILES.get("excel_file"):
        messages.error(request, "Choose an Excel .xlsx file to upload.")
        return redirect("members")
    upload = request.FILES["excel_file"]
    if not upload.name.lower().endswith(".xlsx"):
        messages.error(request, "Please upload an .xlsx Excel file. Older .xls files are not supported.")
        return redirect("members")
    try:
        wb = load_workbook(upload, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        headers = [str(v).strip().lower() if v is not None else "" for v in next(rows, ())]
        required = {"member_no", "name"}
        if not required.issubset(set(headers)):
            messages.error(request, "Excel must contain at least the columns: member_no and name. Download the template for the full format.")
            return redirect("members")
        index = {name: i for i, name in enumerate(headers) if name}
        created = skipped = 0
        errors = []
        for row_no, row in enumerate(rows, start=2):
            if not any(v is not None and str(v).strip() for v in row):
                continue
            def val(key, default=""):
                i = index.get(key)
                return row[i] if i is not None and i < len(row) and row[i] is not None else default
            member_no = str(val("member_no")).strip()
            name = str(val("name")).strip()
            if not member_no or not name:
                skipped += 1
                errors.append(f"Row {row_no}: member_no and name are required.")
                continue
            if Member.objects.filter(member_no=member_no).exists():
                skipped += 1
                errors.append(f"Row {row_no}: member number {member_no} already exists; skipped.")
                continue
            designation = str(val("designation")).strip()
            active_raw = str(val("active", "Yes")).strip().lower()
            active = active_raw not in ("no", "false", "0", "inactive", "n")
            joined_raw = val("joined_on", timezone.localdate())
            if hasattr(joined_raw, "date") and not isinstance(joined_raw, date):
                joined_raw = joined_raw.date()
            try:
                if isinstance(joined_raw, date):
                    joined_on = joined_raw
                elif not str(joined_raw).strip():
                    joined_on = timezone.localdate()
                else:
                    joined_on = date.fromisoformat(str(joined_raw).strip()[:10])
                Member.objects.create(
                    member_no=member_no, name=name, designation=designation,
                    active=active, joined_on=joined_on
                )
                created += 1
            except (ValueError, TypeError) as exc:
                skipped += 1
                errors.append(f"Row {row_no}: invalid joined_on date ({joined_raw}).")
        wb.close()
        messages.success(request, f"Excel import complete: {created} member(s) added, {skipped} row(s) skipped.")
        for err in errors[:8]:
            messages.warning(request, err)
        if len(errors) > 8:
            messages.warning(request, f"{len(errors) - 8} additional row issue(s) not shown.")
    except Exception as exc:
        messages.error(request, f"Could not read this Excel file. Please check that it is a valid .xlsx workbook. Details: {exc}")
    return redirect("members")
def member_add(request):
    form=MemberForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Member saved."); return redirect("members")
    return render(request,"mess/form.html",{"form":form,"title":"Add dining member"})
def stock(request):
    items=StockItem.objects.all()
    additions=StockAddition.objects.select_related("item")[:30]
    return render(request,"mess/stock.html",{"items":items,"additions":additions,"total":sum((i.stock_value for i in items),Decimal("0"))})

def stock_print(request):
    items = StockItem.objects.all()
    additions = StockAddition.objects.select_related("item").order_by("-date", "-id")[:200]
    total = sum((i.stock_value for i in items), Decimal("0"))
    return render(request, "mess/stock_print.html", {
        "items": items, "additions": additions, "total": total,
        "printed_at": timezone.localtime(),
    })
def stock_audit(request):
    """Date-wise stock movement ledger for audit and printing."""
    today = timezone.localdate()
    default_start, default_end = cycle_dates(today)
    try:
        start = date.fromisoformat(request.GET.get("start", default_start.isoformat()))
        end = date.fromisoformat(request.GET.get("end", default_end.isoformat()))
    except ValueError:
        start, end = default_start, default_end
    if end < start:
        start, end = end, start

    selected_item = request.GET.get("item", "all")
    items = StockItem.objects.all()
    if selected_item != "all":
        try:
            selected_item_id = int(selected_item)
            items = items.filter(pk=selected_item_id)
        except (TypeError, ValueError):
            selected_item = "all"
            items = StockItem.objects.all()

    ledger = []
    total_added = Decimal("0")
    total_consumed = Decimal("0")
    total_addition_value = Decimal("0")
    total_consumption_value = Decimal("0")
    for item in items.order_by("name"):
        # Current balance minus all movements from the report start onward gives
        # the opening balance at the beginning of the selected period.
        future_additions = StockAddition.objects.filter(item=item, date__gte=start).aggregate(v=Sum("quantity"))["v"] or Decimal("0")
        future_consumptions = Consumption.objects.filter(item=item, date__gte=start).aggregate(v=Sum("quantity"))["v"] or Decimal("0")
        future_sales = SoldRation.objects.filter(item=item, date__gte=start).aggregate(v=Sum("quantity"))["v"] or Decimal("0")
        balance = item.quantity - future_additions + future_consumptions + future_sales
        ledger.append({"date": start, "item": item, "kind": "Opening balance", "is_opening": True, "quantity_in": balance, "quantity_out": Decimal("0"), "unit_cost": item.average_unit_cost, "value": Decimal("0"), "balance": balance, "notes": ""})
        movements = []
        for addition in StockAddition.objects.filter(item=item, date__range=(start, end)).order_by("date", "id"):
            movements.append({"date": addition.date, "sort_id": addition.id, "item": item, "kind": "Stock entry", "is_opening": False, "quantity_in": addition.quantity, "quantity_out": Decimal("0"), "unit_cost": addition.unit_cost, "value": addition.total_cost, "notes": addition.notes})
        for issue in Consumption.objects.filter(item=item, date__range=(start, end)).order_by("date", "id"):
            movements.append({"date": issue.date, "sort_id": issue.id, "item": item, "kind": "Consumption", "is_opening": False, "quantity_in": Decimal("0"), "quantity_out": issue.quantity, "unit_cost": issue.unit_cost_at_issue, "value": issue.total_cost, "notes": issue.remarks})
        for sale in SoldRation.objects.filter(item=item, date__range=(start, end)).order_by("date", "id"):
            movements.append({"date": sale.date, "sort_id": sale.id, "item": item, "kind": "Sold ration", "is_opening": False, "quantity_in": Decimal("0"), "quantity_out": sale.quantity, "unit_cost": sale.unit_price, "value": sale.total_amount, "notes": sale.name})
        movements.sort(key=lambda r: (r["date"], 0 if r["kind"] == "Stock entry" else (1 if r["kind"] == "Consumption" else 2), r["sort_id"]))
        for row in movements:
            balance += row["quantity_in"] - row["quantity_out"]
            row["balance"] = balance
            ledger.append(row)
            total_added += row["quantity_in"]
            total_consumed += row["quantity_out"]
            if row["kind"] == "Stock entry":
                total_addition_value += row["value"]
            elif row["kind"] == "Consumption":
                total_consumption_value += row["value"]

    ledger.sort(key=lambda r: (r["item"].name.lower(), r["date"], 0 if r.get("is_opening") else 1))
    context = {
        "start": start, "end": end, "items": StockItem.objects.all(),
        "selected_item": selected_item, "ledger": ledger,
        "total_added": total_added, "total_consumed": total_consumed,
        "total_addition_value": total_addition_value,
        "total_consumption_value": total_consumption_value,
        "printed_at": timezone.localtime(),
    }
    return render(request, "mess/stock_audit.html", context)

def stock_add(request):
    form=StockItemForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Stock item saved."); return redirect("stock")
    return render(request,"mess/form.html",{"form":form,"title":"Add stock item / opening balance"})
def stock_add_quantity(request):
    items = StockItem.objects.all()
    if request.method == "POST":
        entry_date = request.POST.get("date") or timezone.localdate().isoformat()
        item_ids = request.POST.getlist("item[]")
        quantities = request.POST.getlist("quantity[]")
        unit_costs = request.POST.getlist("unit_cost[]")
        notes_values = request.POST.getlist("notes[]")
        errors = []
        if not item_ids:
            errors.append("Add at least one item.")
        if not (len(item_ids) == len(quantities) == len(unit_costs)):
            errors.append("Please check the item rows and try again.")
        parsed = []
        try:
            parsed_date = date.fromisoformat(entry_date)
        except ValueError:
            parsed_date = timezone.localdate()
            errors.append("Enter a valid date.")
        for idx, (item_id, qty_raw, cost_raw) in enumerate(zip(item_ids, quantities, unit_costs)):
            try:
                item = StockItem.objects.get(pk=int(item_id))
                qty, cost = Decimal(qty_raw), Decimal(cost_raw)
                if qty <= 0 or cost < 0:
                    raise ValueError
                parsed.append((item, qty, cost, notes_values[idx] if idx < len(notes_values) else ""))
            except (ValueError, TypeError, StockItem.DoesNotExist, ArithmeticError):
                errors.append(f"Row {idx + 1}: choose a valid item and enter a positive quantity and non-negative unit cost.")
        if not errors:
            with transaction.atomic():
                for item, qty, cost, notes_text in parsed:
                    StockAddition.objects.create(date=parsed_date, item=item, quantity=qty, unit_cost=cost, notes=notes_text)
            messages.success(request, f"Saved {len(parsed)} stock item row(s); stock balances updated.")
            return redirect("stock")
        for error in errors:
            messages.error(request, error)
    return render(request, "mess/stock_add_billing.html", {"items": items, "today": timezone.localdate().isoformat()})

def purchases(request): return render(request,"mess/purchases.html",{"rows":Purchase.objects.all(),"total":sum((p.amount for p in Purchase.objects.all()),Decimal("0"))})
def purchase_add(request):
    form=PurchaseForm(request.POST or None,request.FILES or None)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Purchase saved and stock updated."); return redirect("purchases")
    return render(request,"mess/form.html",{"form":form,"title":"Record purchase"})
def consumption(request): return render(request,"mess/consumption.html",{"rows":Consumption.objects.select_related("item"),"total":sum((c.total_cost for c in Consumption.objects.all()),Decimal("0"))})
def consumption_add(request):
    items = StockItem.objects.all()
    if request.method == "POST":
        entry_date = request.POST.get("date") or timezone.localdate().isoformat()
        item_ids = request.POST.getlist("item[]")
        quantities = request.POST.getlist("quantity[]")
        remarks_values = request.POST.getlist("remarks[]")
        errors = []
        try:
            parsed_date = date.fromisoformat(entry_date)
        except ValueError:
            parsed_date = timezone.localdate()
            errors.append("Enter a valid date.")
        if not item_ids:
            errors.append("Add at least one item.")
        if len(item_ids) != len(quantities):
            errors.append("Please check the item rows and try again.")
        parsed = []
        for idx, (item_id, qty_raw) in enumerate(zip(item_ids, quantities)):
            try:
                item = StockItem.objects.get(pk=int(item_id))
                qty = Decimal(qty_raw)
                if qty <= 0:
                    raise ValueError
                remarks = remarks_values[idx] if idx < len(remarks_values) else ""
                parsed.append((item, qty, remarks))
            except (ValueError, TypeError, StockItem.DoesNotExist, ArithmeticError):
                errors.append(f"Row {idx + 1}: choose an item and enter a quantity greater than zero.")
        if not errors:
            try:
                with transaction.atomic():
                    totals = {}
                    for item, qty, _ in parsed:
                        totals[item.pk] = totals.get(item.pk, Decimal("0")) + qty
                    for item_id, qty in totals.items():
                        item = StockItem.objects.select_for_update().get(pk=item_id)
                        if qty > item.quantity:
                            raise ValueError(f"Insufficient stock for {item.name}. Available: {item.quantity} {item.unit}; requested: {qty} {item.unit}.")
                    for item, qty, remarks in parsed:
                        Consumption.objects.create(date=parsed_date, item=item, quantity=qty, remarks=remarks)
                messages.success(request, f"Saved {len(parsed)} consumption item row(s); stock deducted.")
                return redirect("consumption")
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, "mess/consumption_billing.html", {"items": items, "today": timezone.localdate().isoformat()})

def sold_ration(request):
    rows = SoldRation.objects.select_related("item").all()
    total = sum((r.total_amount for r in rows), Decimal("0"))
    return render(request, "mess/sold_ration.html", {"rows": rows, "total": total})

def sold_ration_add(request):
    items = StockItem.objects.all()
    if request.method == "POST":
        entry_date = request.POST.get("date") or timezone.localdate().isoformat()
        buyer_name = request.POST.get("name", "").strip()
        item_ids = request.POST.getlist("item[]")
        quantities = request.POST.getlist("quantity[]")
        errors = []
        try:
            parsed_date = date.fromisoformat(entry_date)
        except ValueError:
            parsed_date = timezone.localdate()
            errors.append("Enter a valid date.")
        if not buyer_name:
            errors.append("Enter the name of the person buying the ration.")
        if not item_ids:
            errors.append("Add at least one item.")
        if len(item_ids) != len(quantities):
            errors.append("Please check the item rows and try again.")
        parsed = []
        for idx, (item_id, qty_raw) in enumerate(zip(item_ids, quantities)):
            try:
                item = StockItem.objects.get(pk=int(item_id))
                qty = Decimal(qty_raw)
                if qty <= 0:
                    raise ValueError
                parsed.append((item, qty))
            except (ValueError, TypeError, StockItem.DoesNotExist, ArithmeticError):
                errors.append(f"Row {idx + 1}: choose an item and enter a quantity greater than zero.")
        if not errors:
            try:
                with transaction.atomic():
                    # Validate cumulative quantities first, including repeated rows for the same item.
                    totals = {}
                    for item, qty in parsed:
                        totals[item.pk] = totals.get(item.pk, Decimal("0")) + qty
                    for item_id, qty in totals.items():
                        item = StockItem.objects.select_for_update().get(pk=item_id)
                        if qty > item.quantity:
                            raise ValueError(f"Insufficient stock for {item.name}. Available: {item.quantity} {item.unit}; requested: {qty} {item.unit}.")
                    for item, qty in parsed:
                        SoldRation.objects.create(date=parsed_date, item=item, quantity=qty, name=buyer_name)
                messages.success(request, f"Saved {len(parsed)} sold-ration item row(s); stock deducted and sale income recorded.")
                return redirect("sold_ration")
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, "mess/sold_ration_billing.html", {"items": items, "today": timezone.localdate().isoformat()})

def attendance(request):
    selected=request.GET.get("date") or timezone.localdate().isoformat()
    try: day=date.fromisoformat(selected)
    except ValueError: day=timezone.localdate(); selected=day.isoformat()
    setting=MessSetting.current(); active=list(Member.objects.filter(active=True)); existing={a.member_id:a for a in Attendance.objects.filter(date=day)}
    if request.method=="POST":
        day=date.fromisoformat(request.POST.get("date",selected)); selected=day.isoformat()
        with transaction.atomic():
            for member in active:
                status=request.POST.get(f"status_{member.id}","ABSENT")
                if status not in ("ABSENT","HALF","FULL"): status="ABSENT"
                Attendance.objects.update_or_create(date=day,member=member,defaults={"status":status,"daily_charge":setting.full_daily_charge})
        messages.success(request,f"Attendance saved for {day:%d %b %Y}."); return redirect(f"/attendance/?date={selected}")
    rows=[]
    for m in active: rows.append({"member":m,"status":existing[m.id].status if m.id in existing else "ABSENT"})
    income=sum(((setting.full_daily_charge if r["status"]=="FULL" else setting.full_daily_charge/Decimal("2") if r["status"]=="HALF" else Decimal("0")) for r in rows),Decimal("0"))
    return render(request,"mess/attendance.html",{"rows":rows,"selected":selected,"charge":setting.full_daily_charge,"income":income})
def payments(request): return render(request,"mess/payments.html",{"rows":Payment.objects.select_related("member"),"total":Payment.objects.aggregate(v=Sum("amount"))["v"] or Decimal("0")})
def payment_add(request):
    form=PaymentForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Member payment recorded."); return redirect("payments")
    return render(request,"mess/form.html",{"form":form,"title":"Record member payment"})
def monthly_summary(request):
    today=timezone.localdate(); default_start,default_end=cycle_dates(today)
    try: start=date.fromisoformat(request.GET.get("start",default_start.isoformat())); end=date.fromisoformat(request.GET.get("end",default_end.isoformat()))
    except ValueError: start,end=default_start,default_end
    if end<start: start,end=end,start
    purchases=list(Purchase.objects.filter(date__range=(start,end)))
    consumptions=list(Consumption.objects.filter(date__range=(start,end)).select_related("item"))
    payments=list(Payment.objects.filter(date__range=(start,end)).select_related("member"))
    attendance_rows=list(Attendance.objects.filter(date__range=(start,end)).select_related("member"))
    sold_rations=list(SoldRation.objects.filter(date__range=(start,end)).select_related("item"))
    sold_ration_income=sum((r.total_amount for r in sold_rations),Decimal("0"))
    purchase_total=sum((p.amount for p in purchases),Decimal("0"))
    consumption_total=sum((c.total_cost for c in consumptions),Decimal("0"))
    income=sum((a.charge for a in attendance_rows),Decimal("0"))
    payment_total=sum((p.amount for p in payments),Decimal("0"))
    stock_value=sum((i.stock_value for i in StockItem.objects.all()),Decimal("0"))
    opening_stock=stock_value + consumption_total - sum((a.total_cost for a in StockAddition.objects.filter(date__range=(start,end))),Decimal("0"))
    # Date-wise operating result includes member charges and sold-ration income.
    daily_rows=[]; day=start
    while day <= end:
        day_income=sum((a.charge for a in attendance_rows if a.date==day),Decimal("0"))
        day_sales=sum((r.total_amount for r in sold_rations if r.date==day),Decimal("0"))
        day_income += day_sales
        day_expense=sum((c.total_cost for c in consumptions if c.date==day),Decimal("0"))
        daily_rows.append({"date":day,"income":day_income,"expense":day_expense,"result":day_income-day_expense,"sold_ration_income":day_sales})
        day += timedelta(days=1)
    return render(request,"mess/summary.html",{"start":start,"end":end,"purchases":purchases,"consumptions":consumptions,"payments":payments,"purchase_total":purchase_total,"consumption_total":consumption_total,"attendance_income":income,"sold_ration_income":sold_ration_income,"sold_rations":sold_rations,"payment_total":payment_total,"stock_value":stock_value,"opening_stock":opening_stock,"operating_result":income+sold_ration_income-consumption_total,"cash_result":payment_total+sold_ration_income-purchase_total,"daily_rows":daily_rows})
def print_charges(request):
    today=timezone.localdate(); default_start,default_end=cycle_dates(today)
    try: start=date.fromisoformat(request.GET.get("start",default_start.isoformat())); end=date.fromisoformat(request.GET.get("end",default_end.isoformat()))
    except ValueError: start,end=default_start,default_end
    rows=[]
    for member in Member.objects.filter(active=True):
        attendances=Attendance.objects.filter(member=member,date__range=(start,end))
        full=attendances.filter(status="FULL").count(); half=attendances.filter(status="HALF").count(); absent=attendances.filter(status="ABSENT").count()
        charge=sum((a.charge for a in attendances),Decimal("0")); paid=Payment.objects.filter(member=member,date__range=(start,end)).aggregate(v=Sum("amount"))["v"] or Decimal("0")
        rows.append({"member":member,"full":full,"half":half,"absent":absent,"charge":charge,"paid":paid,"balance":charge-paid})
    return render(request,"mess/charges_print.html",{"rows":rows,"start":start,"end":end,"setting":MessSetting.current()})
