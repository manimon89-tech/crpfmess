# Mess Account Management (Django)

A starter Django app for a dining mess with purchase, stock, consumption, bill PDF, member, attendance, payment and monthly summary registers.

## Features
- Fixed full-day member charge editable from the dashboard; half-day charge is half of that rate.
- Daily attendance for every active member with Absent / Half / Full selection.
- Purchase register records only purchase date, supplier name, total bill amount, optional notes, and uploaded bill PDF. Purchase bills are separate from item-wise stock entries.
- Stock register has a dedicated “Add stock” action to add quantity item-wise with date and unit cost; stock balance and weighted-average cost update automatically.
- Consumption register deducts stock and records expense at the average unit cost at issue time; insufficient stock is rejected.
- Member payment register records actual money received separately from attendance-based charges.
- Mess accounting period defaults to 26th through 25th.
- Monthly summary shows opening stock estimate, purchase bill totals, closing stock value, consumption expense, attendance-based charges, actual payments, operating result and cash movement. It also displays date-wise daily income, consumption expense and profit/loss, with print support.
- Printable member charge statement (browser Print / Save as PDF).
- Django admin for managing records.

## Run on Windows
1. Install Python 3.10+.
2. Extract the ZIP and open Command Prompt in the project folder.
3. Create and activate a virtual environment:
   ```bat
   py -m venv venv
   venv\Scripts\activate
   ```
4. Install packages:
   ```bat
   pip install -r requirements.txt
   ```
5. Create database tables:
   ```bat
   py manage.py migrate
   ```
6. Create admin login (optional):
   ```bat
   py manage.py createsuperuser
   ```
7. Start the website:
   ```bat
   py manage.py runserver
   ```
8. Open http://127.0.0.1:8000/ . Admin: http://127.0.0.1:8000/admin/ .

## Suggested first setup
1. Open Daily charge and set the current full-day charge.
2. Add members.
3. Add stock items and their opening quantity / average unit cost.
4. Record purchase bill date, supplier, total amount and upload the supplier bill PDF.
5. Use Stock Register → Add stock to add item-wise quantities and unit costs, then record daily consumption.
6. Mark attendance and record actual member payments.
7. Review monthly summary and print member charges.

## Important accounting notes
- Attendance-based charges are accrued income; the payment register is cash actually received. They are intentionally shown separately.
- The app uses a weighted-average stock cost method. Purchase bill totals are not automatically allocated to stock items; stock quantities/costs are entered separately using Add stock. Daily profit/loss is calculated from attendance-based charges less consumption expense.
- The current stock value is live. For reliable historical balance-sheet figures, add a month-end stock snapshot and reconcile stock before closing each cycle. The displayed opening stock is a reconciliation estimate based on current stock, period purchases and consumption.
- Purchase and consumption records are treated as posted transactions. Avoid editing/deleting old transactions directly; corrections should be entered as separate adjustment transactions in a production version.
- Before deployment, set a strong SECRET_KEY, DEBUG=False, configure ALLOWED_HOSTS, secure media storage, authentication/permissions, backups, and HTTPS.


## New features in this update

### Bulk import dining members from Excel
- Open **Members** and download the Excel template.
- Fill in `member_no`, `name`, `designation`, `active`, and `joined_on`.
- Upload an `.xlsx` workbook from the Members page.
- `member_no` and `name` are required. Existing member numbers are skipped to avoid duplicates.
- `active` accepts Yes/No (or true/false). Dates should be Excel dates or `YYYY-MM-DD`.
- Install the new dependency with `pip install -r requirements.txt` (includes openpyxl).

### Print stock register
- Open **Stock register** and click **Print stock register**.
- Use **Print / Save as PDF** in the opened page to print or save a PDF.
- The print view includes current stock balance, weighted-average unit cost, stock value, reorder level, and the latest 200 stock additions.

## Login feature

The application now requires authentication before opening the dashboard or any mess-management page. The login page is available at `/login/`, and the navigation bar includes a Logout button.

Create a user account from the project directory (the folder containing `manage.py`):

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Use the username and password created by `createsuperuser` to sign in at `http://127.0.0.1:8000/login/`. You can also create ordinary user accounts from Django Admin under **Users**. Keep your password private. Existing application pages require a logged-in user; `/admin/` continues to require a staff/superuser account.


## CO / OC / Accountant hierarchy (Version 12)

The application now supports the requested command hierarchy through **Admin → Messes** and **Admin → User mess accesses**.

### Roles
- **Superuser:** unrestricted access to every mess. Select a working mess from the selector below the navigation; operational screens and new entries are scoped to that selected mess to prevent accidental cross-mess transactions. The first active mess is selected initially.
- **CO:** can view the dashboard summary for every mess mapped to that CO username. CO accounts are dashboard-only and cannot open operational pages or change data.
- **OC:** can view the dashboard for the one mess mapped to that OC username. OC accounts are dashboard-only.
- **Accountant:** has full operational access to the one mess mapped to that accountant username.

### Configure users and messes
1. Sign in as Superuser and open `/admin/`.
2. Create each mess under **Messes**. Enter a unique code and name.
3. Create user accounts under **Users**.
4. Open **User mess accesses** and create mapping rows:
   - CO: create one `CO` mapping row for each mess under that CO. A CO may have multiple mess rows.
   - OC: create exactly one `OC` mapping row for the OC's mess.
   - Accountant: create exactly one `ACCOUNTANT` mapping row for the accountant's mess.
5. A user cannot mix CO with OC/Accountant roles. OC and Accountant are restricted to one mess each.
6. Existing non-superuser accounts are migrated as `ACCOUNTANT` for the existing **Default Mess** so they retain access. Change those mappings to the intended roles/messes after migration.

### Data migration and safety
- Migration `0003_mess_hierarchy` creates **Default Mess**, attaches every existing operational record to it, and maps existing ordinary accounts to it as accountants.
- Member numbers and stock item names are now unique within a mess, rather than globally.
- All operational models carry a mess foreign key. Request-level query scoping is applied through tenant middleware, and CO/OC dashboard-only access is enforced server-side.
- Back up `db.sqlite3` and `media/` before migration. Test with separate CO, OC, Accountant and Superuser accounts before live use.
