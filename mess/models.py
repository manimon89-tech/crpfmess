from decimal import Decimal
from contextvars import ContextVar
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

# Set by TenantMiddleware for the duration of each request.
_tenant_scope = ContextVar("mess_tenant_scope", default=None)
_active_mess_id = ContextVar("mess_active_mess_id", default=None)

def set_tenant_context(scope, active_mess_id=None):
    return (_tenant_scope.set(scope), _active_mess_id.set(active_mess_id))

def reset_tenant_context(tokens):
    _tenant_scope.reset(tokens[0])
    _active_mess_id.reset(tokens[1])

def get_active_mess_id():
    return _active_mess_id.get()

class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        scope = _tenant_scope.get()
        if scope is not None:
            return qs.filter(mess_id__in=scope)
        return qs

class Mess(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=30, unique=True, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class UserMessAccess(models.Model):
    CO = "CO"
    OC = "OC"
    ACCOUNTANT = "ACCOUNTANT"
    ROLE_CHOICES = [
        (CO, "Commanding Officer (CO) – dashboards of assigned messes"),
        (OC, "Officer Commanding (OC) – dashboard of one assigned mess"),
        (ACCOUNTANT, "Accountant – full access to one assigned mess"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mess_accesses")
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name="user_accesses")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "mess"], name="uniq_user_mess_access")]
        ordering = ["user__username", "mess__name"]
    def clean(self):
        if self.role in (self.OC, self.ACCOUNTANT) and UserMessAccess.objects.filter(user=self.user, role=self.role).exclude(pk=self.pk).exists():
            raise ValidationError({"role": "OC and Accountant accounts can each be assigned to only one mess."})
        if self.role == self.CO and UserMessAccess.objects.filter(user=self.user).exclude(role=self.CO).exclude(pk=self.pk).exists():
            raise ValidationError({"role": "A CO account cannot also have an OC or Accountant assignment."})
        if self.role != self.CO and UserMessAccess.objects.filter(user=self.user, role=self.CO).exclude(pk=self.pk).exists():
            raise ValidationError({"role": "A user assigned as CO cannot also have an OC or Accountant assignment."})
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    def __str__(self): return f"{self.user.username} – {self.get_role_display()} – {self.mess.name}"

class TenantModel(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name="%(class)s_records")
    objects = TenantManager()
    all_objects = models.Manager()
    class Meta:
        abstract = True
    def save(self, *args, **kwargs):
        if not self.mess_id:
            active_id = get_active_mess_id()
            if active_id:
                self.mess_id = active_id
        if not self.mess_id:
            raise ValidationError("Select a mess before creating this record.")
        super().save(*args, **kwargs)

class MessSetting(TenantModel):
    full_daily_charge = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text="Full-day charge per member")
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return f"{self.mess}: Daily charge ₹{self.full_daily_charge}"
    @classmethod
    def current(cls):
        active_id = get_active_mess_id()
        if active_id:
            obj, _ = cls.objects.get_or_create(mess_id=active_id, defaults={"full_daily_charge": 0})
            return obj
        return cls.objects.order_by("mess_id").first() or cls(full_daily_charge=0)

class Member(TenantModel):
    member_no = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    joined_on = models.DateField(default=timezone.localdate)
    def __str__(self): return f"{self.member_no} - {self.name}"
    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["mess", "member_no"], name="uniq_member_no_per_mess")]

class StockItem(TenantModel):
    name = models.CharField(max_length=150)
    unit = models.CharField(max_length=30, default="kg")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    average_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    @property
    def stock_value(self): return (self.quantity or Decimal('0')) * (self.average_unit_cost or Decimal('0'))
    def __str__(self): return self.name
    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["mess", "name"], name="uniq_stock_name_per_mess")]

class Purchase(TenantModel):
    """Supplier purchase bill register; stock quantities are entered separately."""
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    supplier_name = models.CharField(max_length=150)
    bill_pdf = models.FileField(upload_to="purchase_bills/%Y/%m/", blank=True, null=True)
    notes = models.CharField(max_length=250, blank=True)
    def __str__(self): return f"{self.date} {self.supplier_name} ₹{self.amount}"
    class Meta: ordering = ["-date", "-id"]

class StockAddition(TenantModel):
    date = models.DateField(default=timezone.localdate)
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="stock_additions")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=250, blank=True)
    @property
    def total_cost(self): return self.quantity * self.unit_cost
    def save(self, *args, **kwargs):
        if self.pk is None:
            item = self.item
            if item.mess_id != self.mess_id and self.mess_id:
                raise ValidationError("Stock item belongs to a different mess.")
            old_qty = item.quantity or Decimal("0")
            new_qty = old_qty + self.quantity
            if new_qty > 0:
                item.average_unit_cost = ((old_qty * item.average_unit_cost) + (self.quantity * self.unit_cost)) / new_qty
            item.quantity = new_qty
            item.save(update_fields=["quantity", "average_unit_cost"])
        super().save(*args, **kwargs)
    def __str__(self): return f"{self.date} {self.item} +{self.quantity} {self.item.unit}"
    class Meta: ordering = ["-date", "-id"]

class Consumption(TenantModel):
    date = models.DateField(default=timezone.localdate)
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="consumptions")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost_at_issue = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    remarks = models.CharField(max_length=250, blank=True)
    @property
    def total_cost(self): return self.quantity * self.unit_cost_at_issue
    def save(self, *args, **kwargs):
        if self.pk is None:
            item = self.item
            if item.mess_id != self.mess_id and self.mess_id:
                raise ValidationError("Stock item belongs to a different mess.")
            if self.quantity > item.quantity:
                raise ValueError(f"Insufficient stock for {item.name}. Available: {item.quantity} {item.unit}")
            self.unit_cost_at_issue = item.average_unit_cost
            super().save(*args, **kwargs)
            item.quantity -= self.quantity
            item.save(update_fields=["quantity"])
        else:
            super().save(*args, **kwargs)
    def __str__(self): return f"{self.date} {self.item} {self.quantity}"
    class Meta: ordering = ["-date", "-id"]

class Attendance(TenantModel):
    STATUS = [("ABSENT","Absent"),("HALF","Half charge"),("FULL","Full charge")]
    date = models.DateField(default=timezone.localdate)
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS, default="ABSENT")
    daily_charge = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    class Meta:
        unique_together = ("date", "member")
        ordering = ["member__name"]
    @property
    def charge(self):
        if self.status == "FULL": return self.daily_charge
        if self.status == "HALF": return self.daily_charge / Decimal('2')
        return Decimal('0')

class Payment(TenantModel):
    date = models.DateField(default=timezone.localdate)
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.CharField(max_length=250, blank=True)
    def __str__(self): return f"{self.date} {self.member} ₹{self.amount}"
    class Meta: ordering = ["-date", "-id"]

class SoldRation(TenantModel):
    date = models.DateField(default=timezone.localdate)
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="ration_sales")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    name = models.CharField(max_length=150, help_text="Name of the person buying the ration")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    def save(self, *args, **kwargs):
        if self.pk is None:
            from django.db import transaction
            if not self.mess_id:
                self.mess_id = get_active_mess_id()
            with transaction.atomic():
                item = StockItem.all_objects.select_for_update().get(pk=self.item_id)
                if self.mess_id and item.mess_id != self.mess_id:
                    raise ValidationError("Stock item belongs to a different mess.")
                if self.quantity <= 0: raise ValueError("Quantity must be greater than zero.")
                if self.quantity > item.quantity:
                    raise ValueError(f"Insufficient stock for {item.name}. Available: {item.quantity} {item.unit}")
                self.unit_price = item.average_unit_cost
                self.total_amount = self.quantity * self.unit_price
                super().save(*args, **kwargs)
                item.quantity -= self.quantity
                item.save(update_fields=["quantity"])
        else:
            super().save(*args, **kwargs)
    def __str__(self): return f"{self.date} {self.item} sold to {self.name}: {self.quantity}"
    class Meta: ordering = ["-date", "-id"]
