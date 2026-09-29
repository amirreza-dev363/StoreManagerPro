import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
from datetime import datetime, timedelta
import hashlib
import os
import webbrowser
import shutil
import html


# ---------------- Application paths ----------------
# Keep the executable/install directory read-only friendly (e.g. Program Files).
# User data lives in the Windows per-user application-data directory.
import sys

INSTALL_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
if os.name == "nt":
    APP_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "StoreManager")
else:
    APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".storemanager")
os.makedirs(APP_DATA_DIR, exist_ok=True)

BASE_DIR = APP_DATA_DIR
DATABASE = os.path.join(BASE_DIR, "inventory.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# One-time migration from the old layout (database beside app.py/exe).
LEGACY_DATABASE = os.path.join(INSTALL_DIR, "inventory.db")
if not os.path.exists(DATABASE) and os.path.exists(LEGACY_DATABASE) and os.path.abspath(LEGACY_DATABASE) != os.path.abspath(DATABASE):
    try:
        shutil.copy2(LEGACY_DATABASE, DATABASE)
    except Exception:
        pass

CURRENT_USER = None
USER_PERMISSIONS = {
    "admin": {"all"},
    "manager": {"dashboard", "products", "inventory", "stock", "customers", "sales", "history", "invoice", "payments", "reports", "settings"},
    "sales": {"dashboard", "search", "customers", "sales", "history", "invoice", "payments", "reports"},
    "warehouse": {"dashboard", "products", "inventory", "stock", "search", "history"},
    "viewer": {"dashboard", "search", "history", "customers"},
}
ROLE_NAMES = {
    "admin": "مدیر سیستم",
    "manager": "مدیر فروشگاه",
    "sales": "فروشنده",
    "warehouse": "انباردار",
    "viewer": "مشاهده‌گر",
}


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def has_permission(permission):
    if not CURRENT_USER:
        return False
    role = CURRENT_USER.get("role", "viewer")
    return "all" in USER_PERMISSIONS.get(role, set()) or permission in USER_PERMISSIONS.get(role, set())


def require_permission(permission, parent=None):
    if has_permission(permission):
        return True
    messagebox.showerror("دسترسی غیرمجاز", "سطح کاربری شما اجازه انجام این عملیات را ندارد.", parent=parent or window)
    return False

# ---------------- Jalali calendar helpers ----------------

def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0,31,59,90,120,151,181,212,243,273,304,334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm-1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0,31, 29 if (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)) else 28,31,30,31,30,31,31,30,31,30,31]
    gm = 0
    while gm < 12 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def jalali_today():
    y,m,d = gregorian_to_jalali(datetime.now().year, datetime.now().month, datetime.now().day)
    return f"{y:04d}-{m:02d}-{d:02d}"


def gregorian_date_to_jalali(value):
    if not value:
        return "-"
    try:
        date_part = str(value).split()[0]
        y,m,d = map(int, date_part.split("-")[:3])
        if y < 1700:
            return f"{y:04d}-{m:02d}-{d:02d}"
        jy,jm,jd = gregorian_to_jalali(y,m,d)
        return f"{jy:04d}-{jm:02d}-{jd:02d}"
    except Exception:
        return str(value)


def jalali_date_to_gregorian(value):
    parts = str(value).strip().split("-")
    if len(parts) != 3:
        raise ValueError("فرمت تاریخ باید YYYY-MM-DD باشد.")
    y,m,d = map(int, parts)
    if y >= 1700:
        return f"{y:04d}-{m:02d}-{d:02d}"
    gy,gm,gd = jalali_to_gregorian(y,m,d)
    check = datetime(gy,gm,gd)
    return check.strftime("%Y-%m-%d")


def add_days_to_jalali(value, days):
    g = jalali_date_to_gregorian(value)
    dt = datetime.strptime(g, "%Y-%m-%d") + timedelta(days=days)
    jy,jm,jd = gregorian_to_jalali(dt.year,dt.month,dt.day)
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


def display_sale_date(value):
    return gregorian_date_to_jalali(value)


def display_due_date(value):
    return gregorian_date_to_jalali(value)


def now_storage_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def due_status(due_date, paid_amount, amount):
    if paid_amount >= amount:
        return "پرداخت شد"
    try:
        due = datetime.strptime(str(due_date).split()[0], "%Y-%m-%d").date()
        if due < datetime.now().date():
            return "سررسید گذشته"
    except Exception:
        pass
    if paid_amount > 0:
        return "پرداخت ناقص"
    return "پرداخت نشده"


# ==================================================
# DATABASE
# ==================================================

def connect_database():
    connection = sqlite3.connect(DATABASE, timeout=15)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def create_database():

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            buy_price INTEGER NOT NULL,
            sell_price INTEGER NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(products)")

    columns = [
        column[1]
        for column in cursor.fetchall()
    ]

    if "minimum_stock" not in columns:

        cursor.execute("""
            ALTER TABLE products
            ADD COLUMN minimum_stock INTEGER NOT NULL DEFAULT 0
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (product_id)
            REFERENCES products(id)
        )
    """)
    # جدول دسته‌بندی‌ها
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    # جدول برندها
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    # دسته‌بندی‌های اولیه
    default_categories = [
        "یخچال",
        "فریزر",
        "لباسشویی",
        "ظرفشویی",
        "تلویزیون",
        "اجاق گاز",
        "کولر",
        "جاروبرقی",
        "مایکروویو",
        "سایر"
    ]

    for category in default_categories:
        cursor.execute("""
            INSERT OR IGNORE INTO categories (name)
            VALUES (?)
        """, (category,))

    # برندهای اولیه
    default_brands = [
        "Samsung",
        "LG",
        "Bosch",
        "Daewoo",
        "Snowa",
        "Pakshoma",
        "Electrolux",
        "Other"
    ]

    for brand in default_brands:
        cursor.execute("""
            INSERT OR IGNORE INTO brands (name)
            VALUES (?)
        """, (brand,))

            # ==================================================
    # SALES & CUSTOMERS
    # ==================================================

    # جدول مشتریان
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            national_id TEXT,
            address TEXT,
            notes TEXT
        )
    """)

    # جدول فروش‌ها
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            sale_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            total_amount INTEGER NOT NULL,
            paid_amount INTEGER NOT NULL,
            remaining_amount INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY (customer_id)
            REFERENCES customers(id)
        )
    """)

    # جدول اقلام هر فروش
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            FOREIGN KEY (sale_id)
            REFERENCES sales(id),
            FOREIGN KEY (product_id)
            REFERENCES products(id)
        )
    """)

    # جدول اقساط
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            installment_number INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            paid_amount INTEGER NOT NULL DEFAULT 0,
            payment_date TEXT,
            status TEXT NOT NULL DEFAULT 'پرداخت نشده',
            notes TEXT,
            cash_total INTEGER NOT NULL DEFAULT 0,
            installment_total INTEGER NOT NULL DEFAULT 0,
            down_payment INTEGER NOT NULL DEFAULT 0,
            interval_days INTEGER NOT NULL DEFAULT 0,
            installment_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sale_id)
            REFERENCES sales(id)
        )
    """)

    # سازگاری با دیتابیس‌های قبلی: ستون‌های جدید فروش اقساطی را اضافه کن.
    cursor.execute("PRAGMA table_info(installments)")
    installment_columns = {row[1] for row in cursor.fetchall()}
    installment_migrations = {
        "cash_total": "ALTER TABLE installments ADD COLUMN cash_total INTEGER NOT NULL DEFAULT 0",
        "installment_total": "ALTER TABLE installments ADD COLUMN installment_total INTEGER NOT NULL DEFAULT 0",
        "down_payment": "ALTER TABLE installments ADD COLUMN down_payment INTEGER NOT NULL DEFAULT 0",
        "interval_days": "ALTER TABLE installments ADD COLUMN interval_days INTEGER NOT NULL DEFAULT 0",
        "installment_count": "ALTER TABLE installments ADD COLUMN installment_count INTEGER NOT NULL DEFAULT 0",
    }
    for column, sql in installment_migrations.items():
        if column not in installment_columns:
            cursor.execute(sql)

    cursor.execute("PRAGMA table_info(sales)")
    sales_columns = {row[1] for row in cursor.fetchall()}
    if "cash_total" not in sales_columns:
        cursor.execute("ALTER TABLE sales ADD COLUMN cash_total INTEGER NOT NULL DEFAULT 0")
    if "down_payment" not in sales_columns:
        cursor.execute("ALTER TABLE sales ADD COLUMN down_payment INTEGER NOT NULL DEFAULT 0")
    if "installment_count" not in sales_columns:
        cursor.execute("ALTER TABLE sales ADD COLUMN installment_count INTEGER NOT NULL DEFAULT 0")
    if "installment_interval" not in sales_columns:
        cursor.execute("ALTER TABLE sales ADD COLUMN installment_interval INTEGER NOT NULL DEFAULT 0")

    # کاربران و سطوح دسترسی
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    # مهاجرت امن جدول کاربران قدیمی
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}
    user_migrations = {
        "password_hash": "ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''",
        "full_name": "ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT 'کاربر'",
        "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'",
        "active": "ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
        "created_at": "ALTER TABLE users ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
    }
    for column, sql in user_migrations.items():
        if column not in user_columns:
            cursor.execute(sql)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL UNIQUE,
            invoice_number TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            created_at TEXT NOT NULL,
            details TEXT
        )
    """)
    # دفتر رسمی پرداخت اقساط؛ برای نگهداری چند پرداخت برای یک قسط
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installment_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            installment_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'نقدی',
            reference TEXT,
            notes TEXT,
            recorded_by INTEGER,
            FOREIGN KEY (installment_id) REFERENCES installments(id),
            FOREIGN KEY (recorded_by) REFERENCES users(id)
        )
    """)

    # تنظیمات فروشگاه
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    defaults = {
        'store_name': 'فروشگاه من',
        'store_phone': '',
        'store_address': '',
        'invoice_prefix': 'INV',
        'currency': 'تومان',
    }
    for k,v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (k,v))

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""INSERT INTO users(username,password_hash,full_name,role,active,created_at)
                       VALUES(?,?,?,?,?,?)""",
                       ("admin", hash_password("admin123"), "مدیر سیستم", "admin", 1, now_storage_datetime()))
    # تضمین وجود مدیر پیش‌فرض
    cursor.execute("SELECT id FROM users WHERE username=?", ("admin",))
    admin_row = cursor.fetchone()
    if not admin_row:
        cursor.execute("INSERT INTO users(username,password_hash,full_name,role,active,created_at) VALUES(?,?,?,?,?,?)", ("admin", hash_password("admin123"), "مدیر سیستم", "admin", 1, now_storage_datetime()))
    else:
        cursor.execute("UPDATE users SET password_hash=?, active=1, role='admin' WHERE username='admin' AND (password_hash='' OR password_hash IS NULL)", (hash_password("admin123"),))
    connection.commit()
    connection.close()


def log_action(action, entity_type=None, entity_id=None, details=None):
    try:
        con = connect_database(); cur = con.cursor()
        cur.execute("INSERT INTO audit_logs(username,action,entity_type,entity_id,created_at,details) VALUES(?,?,?,?,?,?)",
                    ((CURRENT_USER or {}).get("username"), action, entity_type, entity_id, now_storage_datetime(), details))
        con.commit(); con.close()
    except Exception:
        pass


# ==================================================
# ADD PRODUCT
# ==================================================

def add_product_window():
    if not require_permission("products", window): return

    add_window = tk.Toplevel(window)

    add_window.title("افزودن کالای جدید")
    add_window.geometry("620x720")
    add_window.minsize(620, 720)
    add_window.configure(bg="#F4F6F8")

    # --------------------------------------------------
    # HEADER
    # --------------------------------------------------

    header = tk.Frame(
        add_window,
        bg="#111827",
        height=105
    )

    header.pack(
        fill="x"
    )

    header.pack_propagate(False)

    header_icon = tk.Label(
        header,
        text="📦",
        font=("Tahoma", 30),
        bg="#111827",
        fg="white"
    )

    header_icon.pack(
        side="right",
        padx=(20, 35),
        pady=20
    )

    header_text = tk.Frame(
        header,
        bg="#111827"
    )

    header_text.pack(
        side="right",
        pady=18
    )

    title = tk.Label(
        header_text,
        text="افزودن کالای جدید",
        font=("Tahoma", 19, "bold"),
        bg="#111827",
        fg="white"
    )

    title.pack(
        anchor="e"
    )

    subtitle = tk.Label(
        header_text,
        text="اطلاعات کالای جدید را وارد کنید",
        font=("Tahoma", 10),
        bg="#111827",
        fg="#CBD5E1"
    )

    subtitle.pack(
        anchor="e",
        pady=(4, 0)
    )

    # --------------------------------------------------
    # MAIN CONTAINER
    # --------------------------------------------------

    container = tk.Frame(
        add_window,
        bg="#F4F6F8"
    )

    container.pack(
        fill="both",
        expand=True,
        padx=35,
        pady=25
    )

    # --------------------------------------------------
    # FORM CARD
    # --------------------------------------------------

    form_card = tk.Frame(
        container,
        bg="white",
        bd=0,
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    form_card.pack(
        fill="both",
        expand=True
    )

    form_card.columnconfigure(0, weight=1)
    form_card.columnconfigure(1, weight=0)

    # --------------------------------------------------
    # VARIABLES
    # --------------------------------------------------

    product_code_var = tk.StringVar()
    name_var = tk.StringVar()
    category_var = tk.StringVar()
    brand_var = tk.StringVar()
    model_var = tk.StringVar()
    quantity_var = tk.StringVar()
    minimum_stock_var = tk.StringVar()
    buy_price_var = tk.StringVar()
    sell_price_var = tk.StringVar()

    # --------------------------------------------------
    # LOAD CATEGORIES AND BRANDS
    # --------------------------------------------------

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM categories
        ORDER BY name
    """)

    categories = [
        row[0]
        for row in cursor.fetchall()
    ]

    cursor.execute("""
        SELECT name
        FROM brands
        ORDER BY name
    """)

    brands = [
        row[0]
        for row in cursor.fetchall()
    ]

    connection.close()

    # --------------------------------------------------
    # SECTION TITLE
    # --------------------------------------------------

    section_title = tk.Label(
        form_card,
        text="اطلاعات پایه کالا",
        font=("Tahoma", 13, "bold"),
        bg="white",
        fg="#111827"
    )

    section_title.grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="e",
        padx=25,
        pady=(22, 15)
    )

    separator = tk.Frame(
        form_card,
        bg="#E5E7EB",
        height=1
    )

    separator.grid(
        row=1,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=25
    )

    # --------------------------------------------------
    # FIELD HELPER
    # --------------------------------------------------

    def create_label(parent, text, row):

        label = tk.Label(
            parent,
            text=text,
            font=("Tahoma", 10, "bold"),
            bg="white",
            fg="#374151",
            anchor="e"
        )

        label.grid(
            row=row,
            column=1,
            padx=(15, 25),
            pady=7,
            sticky="e"
        )

        return label

    def create_entry(parent, variable, row):

        entry = tk.Entry(
            parent,
            textvariable=variable,
            font=("Tahoma", 11),
            bg="#F9FAFB",
            fg="#111827",
            insertbackground="#111827",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#D1D5DB",
            highlightcolor="#6366F1",
            justify="right"
        )

        entry.grid(
            row=row,
            column=0,
            padx=(25, 15),
            pady=7,
            sticky="ew",
            ipady=8
        )

        return entry

    # --------------------------------------------------
    # PRODUCT CODE
    # --------------------------------------------------

    create_label(
        form_card,
        "کد کالا",
        2
    )

    product_code_entry = create_entry(
        form_card,
        product_code_var,
        2
    )

    # --------------------------------------------------
    # PRODUCT NAME
    # --------------------------------------------------

    create_label(
        form_card,
        "نام کالا",
        3
    )

    name_entry = create_entry(
        form_card,
        name_var,
        3
    )

    # --------------------------------------------------
    # CATEGORY
    # --------------------------------------------------

    create_label(
        form_card,
        "دسته‌بندی",
        4
    )

    category_combo = ttk.Combobox(
        form_card,
        textvariable=category_var,
        values=categories,
        state="readonly",
        font=("Tahoma", 11),
        justify="right"
    )

    category_combo.grid(
        row=4,
        column=0,
        padx=(25, 15),
        pady=7,
        sticky="ew",
        ipady=5
    )

    # --------------------------------------------------
    # BRAND
    # --------------------------------------------------

    create_label(
        form_card,
        "برند",
        5
    )

    brand_combo = ttk.Combobox(
        form_card,
        textvariable=brand_var,
        values=brands,
        state="readonly",
        font=("Tahoma", 11),
        justify="right"
    )

    brand_combo.grid(
        row=5,
        column=0,
        padx=(25, 15),
        pady=7,
        sticky="ew",
        ipady=5
    )

    # --------------------------------------------------
    # MODEL
    # --------------------------------------------------

    create_label(
        form_card,
        "مدل",
        6
    )

    model_entry = create_entry(
        form_card,
        model_var,
        6
    )

    # --------------------------------------------------
    # SECTION: INVENTORY
    # --------------------------------------------------

    inventory_section = tk.Label(
        form_card,
        text="اطلاعات موجودی و قیمت",
        font=("Tahoma", 13, "bold"),
        bg="white",
        fg="#111827"
    )

    inventory_section.grid(
        row=7,
        column=0,
        columnspan=2,
        sticky="e",
        padx=25,
        pady=(18, 10)
    )

    separator2 = tk.Frame(
        form_card,
        bg="#E5E7EB",
        height=1
    )

    separator2.grid(
        row=8,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=25
    )

    # --------------------------------------------------
    # QUANTITY
    # --------------------------------------------------

    create_label(
        form_card,
        "تعداد موجودی",
        9
    )

    quantity_entry = create_entry(
        form_card,
        quantity_var,
        9
    )

    # --------------------------------------------------
    # MINIMUM STOCK
    # --------------------------------------------------

    create_label(
        form_card,
        "حداقل موجودی",
        10
    )

    minimum_stock_entry = create_entry(
        form_card,
        minimum_stock_var,
        10
    )

    # --------------------------------------------------
    # BUY PRICE
    # --------------------------------------------------

    create_label(
        form_card,
        "قیمت خرید",
        11
    )

    buy_price_entry = create_entry(
        form_card,
        buy_price_var,
        11
    )

    # --------------------------------------------------
    # SELL PRICE
    # --------------------------------------------------

    create_label(
        form_card,
        "قیمت فروش",
        12
    )

    sell_price_entry = create_entry(
        form_card,
        sell_price_var,
        12
    )

    # --------------------------------------------------
    # SAVE PRODUCT
    # --------------------------------------------------

    def save_product():

        product_code = product_code_var.get().strip()
        name = name_var.get().strip()
        category = category_var.get().strip()
        brand = brand_var.get().strip()
        model = model_var.get().strip()

        quantity_text = quantity_var.get().strip()
        minimum_stock_text = minimum_stock_var.get().strip()
        buy_price_text = buy_price_var.get().strip()
        sell_price_text = sell_price_var.get().strip()

        # ------------------------------
        # REQUIRED FIELDS
        # ------------------------------

        if not product_code:

            messagebox.showerror(
                "اطلاعات ناقص",
                "کد کالا را وارد کنید.",
                parent=add_window
            )

            product_code_entry.focus()
            return

        if not name:

            messagebox.showerror(
                "اطلاعات ناقص",
                "نام کالا را وارد کنید.",
                parent=add_window
            )

            name_entry.focus()
            return

        if not category:

            messagebox.showerror(
                "اطلاعات ناقص",
                "یک دسته‌بندی انتخاب کنید.",
                parent=add_window
            )

            category_combo.focus()
            return

        if not brand:

            messagebox.showerror(
                "اطلاعات ناقص",
                "یک برند انتخاب کنید.",
                parent=add_window
            )

            brand_combo.focus()
            return

        if not model:

            messagebox.showerror(
                "اطلاعات ناقص",
                "مدل کالا را وارد کنید.",
                parent=add_window
            )

            model_entry.focus()
            return

        # ------------------------------
        # NUMBER VALIDATION
        # ------------------------------

        try:

            quantity = int(quantity_text)
            minimum_stock = int(minimum_stock_text)
            buy_price = int(buy_price_text)
            sell_price = int(sell_price_text)

        except ValueError:

            messagebox.showerror(
                "خطای اطلاعات",
                "تعداد و قیمت‌ها باید به صورت عدد وارد شوند.",
                parent=add_window
            )

            return

        if quantity < 0:

            messagebox.showerror(
                "خطای اطلاعات",
                "تعداد موجودی نمی‌تواند منفی باشد.",
                parent=add_window
            )

            quantity_entry.focus()
            return

        if minimum_stock < 0:

            messagebox.showerror(
                "خطای اطلاعات",
                "حداقل موجودی نمی‌تواند منفی باشد.",
                parent=add_window
            )

            minimum_stock_entry.focus()
            return

        if buy_price < 0 or sell_price < 0:

            messagebox.showerror(
                "خطای اطلاعات",
                "قیمت‌ها نمی‌توانند منفی باشند.",
                parent=add_window
            )

            return

        # --------------------------------------------------
        # SAVE TO DATABASE
        # --------------------------------------------------

        connection = connect_database()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO products
                (
                    product_code,
                    name,
                    category,
                    brand,
                    model,
                    quantity,
                    minimum_stock,
                    buy_price,
                    sell_price
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_code,
                name,
                category,
                brand,
                model,
                quantity,
                minimum_stock,
                buy_price,
                sell_price
            ))

            product_id = cursor.lastrowid

            # ثبت ورود اولیه در تاریخچه

            if quantity > 0:

                cursor.execute("""
                    INSERT INTO stock_movements
                    (
                        product_id,
                        movement_type,
                        quantity,
                        date
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    product_id,
                    "ورود اولیه",
                    quantity,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ))

            connection.commit()

            messagebox.showinfo(
                "ثبت موفق",
                (
                    f"کالای «{name}» با موفقیت ثبت شد.\n\n"
                    f"کد کالا: {product_code}\n"
                    f"موجودی اولیه: {quantity}"
                ),
                parent=add_window
            )

            # پاک کردن فرم

            product_code_var.set("")
            name_var.set("")
            category_var.set("")
            brand_var.set("")
            model_var.set("")
            quantity_var.set("")
            minimum_stock_var.set("")
            buy_price_var.set("")
            sell_price_var.set("")

            product_code_entry.focus()

        except sqlite3.IntegrityError:

            messagebox.showerror(
                "کد کالا تکراری",
                (
                    "این کد کالا قبلاً در سیستم ثبت شده است.\n\n"
                    "لطفاً یک کد کالای دیگر وارد کنید."
                ),
                parent=add_window
            )

            product_code_entry.focus()

        finally:

            connection.close()

    # --------------------------------------------------
    # BUTTON AREA
    # --------------------------------------------------

    button_frame = tk.Frame(
        container,
        bg="#F4F6F8"
    )

    button_frame.pack(
        fill="x",
        pady=(18, 0)
    )

    save_button = tk.Button(
        button_frame,
        text="✓  ثبت کالا",
        font=("Tahoma", 12, "bold"),
        bg="#4F46E5",
        fg="white",
        activebackground="#4338CA",
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=save_product
    )

    save_button.pack(
        side="right",
        ipadx=30,
        ipady=9
    )

    cancel_button = tk.Button(
        button_frame,
        text="انصراف",
        font=("Tahoma", 11, "bold"),
        bg="#E5E7EB",
        fg="#374151",
        activebackground="#D1D5DB",
        activeforeground="#111827",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=add_window.destroy
    )

    cancel_button.pack(
        side="left",
        ipadx=25,
        ipady=9
    )

    # --------------------------------------------------
    # KEYBOARD SHORTCUT
    # --------------------------------------------------

    add_window.bind(
        "<Return>",
        lambda event: save_product()
    )

    add_window.bind(
        "<Escape>",
        lambda event: add_window.destroy()
    )

    # --------------------------------------------------
    # INITIAL FOCUS
    # --------------------------------------------------

    product_code_entry.focus()


# ==================================================
# INVENTORY
# ==================================================

inventory_window = None
inventory_tree = None


def inventory_window_exists():

    global inventory_window

    try:

        if inventory_window is not None:
            return inventory_window.winfo_exists()

    except tk.TclError:
        pass

    return False


def load_products():

    global inventory_tree

    if inventory_tree is None:
        return

    for item in inventory_tree.get_children():
        inventory_tree.delete(item)

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            product_code,
            name,
            category,
            brand,
            model,
            quantity,
            minimum_stock,
            buy_price,
            sell_price
        FROM products
        ORDER BY id
    """)

    products = cursor.fetchall()

    connection.close()

    for product in products:

        product_id = product[0]
        quantity = product[6]
        minimum_stock = product[7]

        if quantity == 0:
            status = "ناموجود"

        elif quantity <= minimum_stock:
            status = "موجودی کم"

        else:
            status = "موجود"

        inventory_tree.insert(
            "",
            "end",
            iid=str(product_id),
            values=(
                product[1],
                product[2],
                product[3],
                product[4],
                product[5],
                product[6],
                product[7],
                product[8],
                product[9],
                status
            )
        )


# ==================================================
# EDIT PRODUCT
# ==================================================

def edit_product():
    if not require_permission("products", window): return

    if inventory_tree is None:
        return

    selected = inventory_tree.selection()

    if not selected:

        messagebox.showwarning(
            "انتخاب کالا",
            "ابتدا یک کالا را از جدول انتخاب کنید.",
            parent=inventory_window
        )

        return

    product_id = selected[0]

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            product_code,
            name,
            category,
            brand,
            model,
            quantity,
            minimum_stock,
            buy_price,
            sell_price
        FROM products
        WHERE id = ?
    """, (product_id,))

    product = cursor.fetchone()

    # دریافت دسته‌بندی‌ها
    cursor.execute("""
        SELECT name
        FROM categories
        ORDER BY name
    """)

    categories = [
        row[0]
        for row in cursor.fetchall()
    ]

    # دریافت برندها
    cursor.execute("""
        SELECT name
        FROM brands
        ORDER BY name
    """)

    brands = [
        row[0]
        for row in cursor.fetchall()
    ]

    connection.close()

    if product is None:

        messagebox.showerror(
            "خطا",
            "کالا پیدا نشد.",
            parent=inventory_window
        )

        return

    edit_window = tk.Toplevel(
        inventory_window
    )

    edit_window.title(
        "ویرایش کالا"
    )

    edit_window.geometry(
        "500x600"
    )

    edit_window.resizable(
        False,
        False
    )

    title = tk.Label(
        edit_window,
        text="✏️ ویرایش کالا",
        font=("Tahoma", 20, "bold")
    )

    title.pack(
        pady=20
    )

    form_frame = tk.Frame(
        edit_window
    )

    form_frame.pack(
        pady=10
    )

    product_code_var = tk.StringVar(
        value=product[1]
    )

    name_var = tk.StringVar(
        value=product[2]
    )

    category_var = tk.StringVar(
        value=product[3]
    )

    brand_var = tk.StringVar(
        value=product[4]
    )

    model_var = tk.StringVar(
        value=product[5]
    )

    quantity_var = tk.StringVar(
        value=str(product[6])
    )

    minimum_stock_var = tk.StringVar(
        value=str(product[7])
    )

    buy_price_var = tk.StringVar(
        value=str(product[8])
    )

    sell_price_var = tk.StringVar(
        value=str(product[9])
    )

    # ----------------------------------------------
    # کد کالا
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="کد کالا:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=0,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=product_code_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=0,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # نام کالا
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="نام کالا:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=1,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=name_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=1,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # دسته‌بندی
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="دسته‌بندی:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=2,
        column=1,
        padx=10,
        pady=7
    )

    category_combo = ttk.Combobox(
        form_frame,
        textvariable=category_var,
        values=categories,
        state="readonly",
        font=("Tahoma", 11),
        width=23
    )

    category_combo.grid(
        row=2,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # برند
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="برند:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=3,
        column=1,
        padx=10,
        pady=7
    )

    brand_combo = ttk.Combobox(
        form_frame,
        textvariable=brand_var,
        values=brands,
        state="readonly",
        font=("Tahoma", 11),
        width=23
    )

    brand_combo.grid(
        row=3,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # مدل
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="مدل:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=4,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=model_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=4,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # تعداد
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="تعداد:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=5,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=quantity_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=5,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # حداقل موجودی
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="حداقل موجودی:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=6,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=minimum_stock_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=6,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # قیمت خرید
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="قیمت خرید:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=7,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=buy_price_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=7,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # قیمت فروش
    # ----------------------------------------------

    label = tk.Label(
        form_frame,
        text="قیمت فروش:",
        font=("Tahoma", 11),
        width=16,
        anchor="e"
    )

    label.grid(
        row=8,
        column=1,
        padx=10,
        pady=7
    )

    entry = tk.Entry(
        form_frame,
        textvariable=sell_price_var,
        font=("Tahoma", 11),
        width=25,
        justify="right"
    )

    entry.grid(
        row=8,
        column=0,
        padx=10,
        pady=7
    )

    # ----------------------------------------------
    # ذخیره تغییرات
    # ----------------------------------------------

    def update_product():

        product_code = product_code_var.get().strip()
        name = name_var.get().strip()
        category = category_var.get().strip()
        brand = brand_var.get().strip()
        model = model_var.get().strip()

        try:

            quantity = int(
                quantity_var.get().strip()
            )

            minimum_stock = int(
                minimum_stock_var.get().strip()
            )

            buy_price = int(
                buy_price_var.get().strip()
            )

            sell_price = int(
                sell_price_var.get().strip()
            )

        except ValueError:

            messagebox.showerror(
                "خطا",
                "تعداد و قیمت‌ها باید عدد باشند.",
                parent=edit_window
            )

            return

        if not product_code or not name:

            messagebox.showerror(
                "خطا",
                "کد و نام کالا نمی‌توانند خالی باشند.",
                parent=edit_window
            )

            return

        if not category:

            messagebox.showerror(
                "خطا",
                "یک دسته‌بندی انتخاب کنید.",
                parent=edit_window
            )

            return

        if not brand:

            messagebox.showerror(
                "خطا",
                "یک برند انتخاب کنید.",
                parent=edit_window
            )

            return

        if quantity < 0:

            messagebox.showerror(
                "خطا",
                "تعداد نمی‌تواند منفی باشد.",
                parent=edit_window
            )

            return

        if minimum_stock < 0:

            messagebox.showerror(
                "خطا",
                "حداقل موجودی نمی‌تواند منفی باشد.",
                parent=edit_window
            )

            return

        if buy_price < 0 or sell_price < 0:

            messagebox.showerror(
                "خطا",
                "قیمت نمی‌تواند منفی باشد.",
                parent=edit_window
            )

            return

        connection = connect_database()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                UPDATE products
                SET
                    product_code = ?,
                    name = ?,
                    category = ?,
                    brand = ?,
                    model = ?,
                    quantity = ?,
                    minimum_stock = ?,
                    buy_price = ?,
                    sell_price = ?
                WHERE id = ?
            """, (
                product_code,
                name,
                category,
                brand,
                model,
                quantity,
                minimum_stock,
                buy_price,
                sell_price,
                product_id
            ))

            connection.commit()

            messagebox.showinfo(
                "موفق",
                "اطلاعات کالا با موفقیت ویرایش شد.",
                parent=edit_window
            )

            edit_window.destroy()

            load_products()

        except sqlite3.IntegrityError:

            messagebox.showerror(
                "خطا",
                "این کد کالا متعلق به کالای دیگری است.",
                parent=edit_window
            )

        finally:

            connection.close()

    update_button = tk.Button(
        edit_window,
        text="💾 ذخیره تغییرات",
        font=("Tahoma", 13, "bold"),
        width=20,
        height=2,
        command=update_product
    )

    update_button.pack(
        pady=20
    )


# ==================================================
# DELETE PRODUCT
# ==================================================

def delete_product():
    if not require_permission("products", window): return

    if inventory_tree is None:
        return

    selected = inventory_tree.selection()

    if not selected:

        messagebox.showwarning(
            "انتخاب کالا",
            "ابتدا یک کالا را از جدول انتخاب کنید.",
            parent=inventory_window
        )

        return

    product_id = selected[0]

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            product_code,
            name,
            quantity
        FROM products
        WHERE id = ?
    """, (product_id,))

    product = cursor.fetchone()

    connection.close()

    if product is None:

        messagebox.showerror(
            "خطا",
            "کالا پیدا نشد.",
            parent=inventory_window
        )

        return

    product_code = product[0]
    product_name = product[1]
    quantity = product[2]

    answer = messagebox.askyesno(
        "تأیید حذف",
        (
            f"آیا مطمئن هستید که می‌خواهید این کالا حذف شود؟\n\n"
            f"کد: {product_code}\n"
            f"نام: {product_name}\n"
            f"موجودی: {quantity}\n\n"
            f"این عملیات قابل برگشت نیست."
        ),
        parent=inventory_window
    )

    if not answer:
        return

    connection = connect_database()
    cursor = connection.cursor()

    try:

        # حذف تاریخچه مربوط به کالا

        cursor.execute("""
            DELETE FROM stock_movements
            WHERE product_id = ?
        """, (product_id,))

        # حذف خود کالا

        cursor.execute("""
            DELETE FROM products
            WHERE id = ?
        """, (product_id,))

        connection.commit()

        messagebox.showinfo(
            "موفق",
            "کالا با موفقیت حذف شد.",
            parent=inventory_window
        )

        load_products()

    finally:

        connection.close()


# ==================================================
# INVENTORY WINDOW
# ==================================================

def show_inventory():
    if not require_permission("inventory", window): return

    global inventory_window
    global inventory_tree

    # اگر پنجره از قبل باز است، همان را فعال کن
    if inventory_window_exists():

        inventory_window.lift()
        inventory_window.focus_force()
        load_products()

        return

    # ==================================================
    # INVENTORY WINDOW
    # ==================================================

    inventory_window = tk.Toplevel(window)

    inventory_window.title(
        "مدیریت موجودی کالاها"
    )

    inventory_window.geometry(
        "1400x780"
    )

    inventory_window.minsize(
        1100,
        650
    )

    inventory_window.configure(
        bg="#F5F7FA"
    )


    # ==================================================
    # COLORS
    # ==================================================

    BG = "#F5F7FA"
    WHITE = "#FFFFFF"

    TEXT_DARK = "#1F2937"
    TEXT_GRAY = "#6B7280"

    PRIMARY = "#4F46E5"
    PRIMARY_HOVER = "#4338CA"

    GREEN = "#10B981"
    GREEN_HOVER = "#059669"

    RED = "#EF4444"
    RED_HOVER = "#DC2626"

    BORDER = "#E5E7EB"


    # ==================================================
    # HEADER
    # ==================================================

    header = tk.Frame(
        inventory_window,
        bg=WHITE,
        height=95
    )

    header.pack(
        fill="x"
    )

    header.pack_propagate(False)


    # -----------------------------
    # Header right
    # -----------------------------

    header_right = tk.Frame(
        header,
        bg=WHITE
    )

    header_right.pack(
        side="right",
        padx=30
    )


    icon_label = tk.Label(
        header_right,
        text="📦",
        font=("Tahoma", 30),
        bg=WHITE
    )

    icon_label.pack(
        side="right",
        padx=(15, 0)
    )


    title_frame = tk.Frame(
        header_right,
        bg=WHITE
    )

    title_frame.pack(
        side="right"
    )


    title_label = tk.Label(
        title_frame,
        text="مدیریت موجودی کالاها",
        font=("Tahoma", 20, "bold"),
        bg=WHITE,
        fg=TEXT_DARK
    )

    title_label.pack(
        anchor="e"
    )


    subtitle_label = tk.Label(
        title_frame,
        text="مشاهده، ویرایش و مدیریت موجودی فروشگاه",
        font=("Tahoma", 10),
        bg=WHITE,
        fg=TEXT_GRAY
    )

    subtitle_label.pack(
        anchor="e",
        pady=(3, 0)
    )


    # -----------------------------
    # Header left
    # -----------------------------

    header_left = tk.Frame(
        header,
        bg=WHITE
    )

    header_left.pack(
        side="left",
        padx=30
    )


    live_label = tk.Label(
        header_left,
        text="● اطلاعات زنده",
        font=("Tahoma", 10, "bold"),
        bg=WHITE,
        fg=GREEN
    )

    live_label.pack()


    # ==================================================
    # MAIN CONTENT
    # ==================================================

    main_frame = tk.Frame(
        inventory_window,
        bg=BG
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=30,
        pady=25
    )


    # ==================================================
    # TOP INFORMATION CARDS
    # ==================================================

    stats_frame = tk.Frame(
        main_frame,
        bg=BG
    )

    stats_frame.pack(
        fill="x",
        pady=(0, 20)
    )


    # -----------------------------
    # Variables
    # -----------------------------

    total_products_var = tk.StringVar(
        value="0"
    )

    total_quantity_var = tk.StringVar(
        value="0"
    )

    low_stock_var = tk.StringVar(
        value="0"
    )

    out_of_stock_var = tk.StringVar(
        value="0"
    )


    def create_stat_card(
        parent,
        title,
        variable,
        icon,
        bg_color,
        column
    ):

        card = tk.Frame(
            parent,
            bg=WHITE,
            highlightbackground=BORDER,
            highlightthickness=1,
            height=90
        )

        card.grid(
            row=0,
            column=column,
            padx=6,
            sticky="nsew"
        )

        card.grid_propagate(False)


        icon_label = tk.Label(
            card,
            text=icon,
            font=("Tahoma", 22),
            bg=WHITE
        )

        icon_label.pack(
            side="right",
            padx=15
        )


        text_frame = tk.Frame(
            card,
            bg=WHITE
        )

        text_frame.pack(
            side="right",
            fill="both",
            expand=True
        )


        title_label = tk.Label(
            text_frame,
            text=title,
            font=("Tahoma", 9),
            bg=WHITE,
            fg=TEXT_GRAY
        )

        title_label.pack(
            anchor="e",
            pady=(13, 0)
        )


        value_label = tk.Label(
            text_frame,
            textvariable=variable,
            font=("Tahoma", 17, "bold"),
            bg=WHITE,
            fg=bg_color
        )

        value_label.pack(
            anchor="e"
        )


    for i in range(4):

        stats_frame.columnconfigure(
            i,
            weight=1
        )


    create_stat_card(
        stats_frame,
        "تعداد کالاها",
        total_products_var,
        "📦",
        PRIMARY,
        0
    )


    create_stat_card(
        stats_frame,
        "مجموع موجودی",
        total_quantity_var,
        "🔢",
        GREEN,
        1
    )


    create_stat_card(
        stats_frame,
        "موجودی کم",
        low_stock_var,
        "⚠️",
        "#F59E0B",
        2
    )


    create_stat_card(
        stats_frame,
        "ناموجود",
        out_of_stock_var,
        "❌",
        RED,
        3
    )


    # ==================================================
    # TOOLBAR
    # ==================================================

    toolbar = tk.Frame(
        main_frame,
        bg=WHITE,
        highlightbackground=BORDER,
        highlightthickness=1
    )

    toolbar.pack(
        fill="x",
        pady=(0, 12)
    )


    # -----------------------------
    # Search area
    # -----------------------------

    search_area = tk.Frame(
        toolbar,
        bg=WHITE
    )

    search_area.pack(
        side="right",
        padx=15,
        pady=12
    )


    search_label = tk.Label(
        search_area,
        text="🔍",
        font=("Tahoma", 16),
        bg=WHITE
    )

    search_label.pack(
        side="right",
        padx=(0, 8)
    )


    inventory_search_var = tk.StringVar()


    search_entry = tk.Entry(
        search_area,
        textvariable=inventory_search_var,
        font=("Tahoma", 11),
        width=35,
        justify="right",
        relief="flat",
        bd=0,
        bg="#F3F4F6"
    )

    search_entry.pack(
        side="right",
        ipady=8,
        padx=5
    )


    # -----------------------------
    # Buttons area
    # -----------------------------

    action_area = tk.Frame(
        toolbar,
        bg=WHITE
    )

    action_area.pack(
        side="left",
        padx=15,
        pady=10
    )


    # ==================================================
    # BUTTON CREATOR
    # ==================================================

    def create_action_button(
        parent,
        text,
        bg,
        hover_bg,
        command
    ):

        button = tk.Button(
            parent,
            text=text,
            font=("Tahoma", 10, "bold"),
            bg=bg,
            fg=TEXT_DARK,
            activebackground=hover_bg,
            activeforeground=WHITE,
            relief="flat",
            bd=0,
            cursor="hand2",
            width=14,
            height=1,
            command=command
        )

        button.pack(
            side="left",
            padx=4,
            ipady=5
        )


        def enter(event):

            button.configure(
                bg=hover_bg,
                fg=WHITE
            )


        def leave(event):

            button.configure(
                bg=bg,
                fg=TEXT_DARK
            )


        button.bind(
            "<Enter>",
            enter
        )

        button.bind(
            "<Leave>",
            leave
        )

        return button


    # ==================================================
    # TABLE FRAME
    # ==================================================

    table_container = tk.Frame(
        main_frame,
        bg=WHITE,
        highlightbackground=BORDER,
        highlightthickness=1
    )

    table_container.pack(
        fill="both",
        expand=True
    )


    # ==================================================
    # TABLE TITLE
    # ==================================================

    table_header = tk.Frame(
        table_container,
        bg=WHITE,
        height=45
    )

    table_header.pack(
        fill="x"
    )

    table_header.pack_propagate(False)


    table_title = tk.Label(
        table_header,
        text="📋 فهرست کالاها",
        font=("Tahoma", 12, "bold"),
        bg=WHITE,
        fg=TEXT_DARK
    )

    table_title.pack(
        side="right",
        padx=15,
        pady=10
    )


    result_count_var = tk.StringVar(
        value="0 کالا"
    )


    result_count_label = tk.Label(
        table_header,
        textvariable=result_count_var,
        font=("Tahoma", 9),
        bg=WHITE,
        fg=TEXT_GRAY
    )

    result_count_label.pack(
        side="left",
        padx=15
    )


    # ==================================================
    # TREEVIEW STYLE
    # ==================================================

    style = ttk.Style()

    style.configure(
        "Inventory.Treeview",
        font=("Tahoma", 10),
        rowheight=38,
        background="#FFFFFF",
        fieldbackground="#FFFFFF",
        foreground=TEXT_DARK
    )

    style.configure(
        "Inventory.Treeview.Heading",
        font=("Tahoma", 10, "bold"),
        background="#F1F5F9",
        foreground=TEXT_DARK,
        relief="flat",
        padding=8
    )

    style.map(
        "Inventory.Treeview",
        background=[
            ("selected", "#EEF2FF")
        ],
        foreground=[
            ("selected", TEXT_DARK)
        ]
    )


    # ==================================================
    # COLUMNS
    # ==================================================

    columns = (
        "product_code",
        "name",
        "category",
        "brand",
        "model",
        "quantity",
        "minimum_stock",
        "buy_price",
        "sell_price",
        "status"
    )


    inventory_tree = ttk.Treeview(
        table_container,
        columns=columns,
        show="headings",
        style="Inventory.Treeview",
        selectmode="browse"
    )


    headings = {
        "product_code": "کد کالا",
        "name": "نام کالا",
        "category": "دسته‌بندی",
        "brand": "برند",
        "model": "مدل",
        "quantity": "موجودی",
        "minimum_stock": "حداقل",
        "buy_price": "قیمت خرید",
        "sell_price": "قیمت فروش",
        "status": "وضعیت"
    }


    for column, heading in headings.items():

        inventory_tree.heading(
            column,
            text=heading
        )


    # ==================================================
    # COLUMN WIDTHS
    # ==================================================

    widths = {
        "product_code": 100,
        "name": 180,
        "category": 120,
        "brand": 110,
        "model": 120,
        "quantity": 80,
        "minimum_stock": 80,
        "buy_price": 125,
        "sell_price": 125,
        "status": 105
    }


    for column, width in widths.items():

        inventory_tree.column(
            column,
            width=width,
            minwidth=60,
            anchor="center"
        )


    # نام کالا راست‌چین
    inventory_tree.column(
        "name",
        anchor="e"
    )


    # ==================================================
    # SCROLLBARS
    # ==================================================

    scrollbar_y = ttk.Scrollbar(
        table_container,
        orient="vertical",
        command=inventory_tree.yview
    )


    scrollbar_x = ttk.Scrollbar(
        table_container,
        orient="horizontal",
        command=inventory_tree.xview
    )


    inventory_tree.configure(
        yscrollcommand=scrollbar_y.set,
        xscrollcommand=scrollbar_x.set
    )


    inventory_tree.pack(
        side="top",
        fill="both",
        expand=True
    )


    scrollbar_y.pack(
        side="right",
        fill="y"
    )


    scrollbar_x.pack(
        side="bottom",
        fill="x"
    )


    # ==================================================
    # STATUS COLORS
    # ==================================================

    inventory_tree.tag_configure(
        "available",
        foreground="#047857"
    )

    inventory_tree.tag_configure(
        "low",
        foreground="#B45309"
    )

    inventory_tree.tag_configure(
        "empty",
        foreground="#DC2626"
    )


    # ==================================================
    # LOAD INVENTORY
    # ==================================================

    def refresh_inventory():

        for item in inventory_tree.get_children():

            inventory_tree.delete(item)


        connection = connect_database()

        cursor = connection.cursor()


        cursor.execute("""
            SELECT
                id,
                product_code,
                name,
                category,
                brand,
                model,
                quantity,
                minimum_stock,
                buy_price,
                sell_price
            FROM products
            ORDER BY id DESC
        """)


        products = cursor.fetchall()

        connection.close()


        total_products = len(products)

        total_quantity = sum(
            product[6]
            for product in products
        )

        low_stock = sum(
            1
            for product in products
            if product[6] > 0
            and product[6] <= product[7]
        )

        out_of_stock = sum(
            1
            for product in products
            if product[6] == 0
        )


        total_products_var.set(
            f"{total_products:,}"
        )

        total_quantity_var.set(
            f"{total_quantity:,}"
        )

        low_stock_var.set(
            f"{low_stock:,}"
        )

        out_of_stock_var.set(
            f"{out_of_stock:,}"
        )


        for product in products:

            product_id = product[0]

            quantity = product[6]

            minimum_stock = product[7]


            if quantity == 0:

                status = "ناموجود"

                tag = "empty"

            elif quantity <= minimum_stock:

                status = "موجودی کم"

                tag = "low"

            else:

                status = "موجود"

                tag = "available"


            inventory_tree.insert(
                "",
                "end",
                iid=str(product_id),
                values=(
                    product[1],
                    product[2],
                    product[3],
                    product[4],
                    product[5],
                    f"{product[6]:,}",
                    f"{product[7]:,}",
                    f"{product[8]:,}",
                    f"{product[9]:,}",
                    status
                ),
                tags=(tag,)
            )


        result_count_var.set(
            f"{total_products:,} کالا"
        )


    # ==================================================
    # SEARCH INVENTORY
    # ==================================================

    def search_inventory(*args):

        text = inventory_search_var.get().strip()


        for item in inventory_tree.get_children():

            inventory_tree.delete(item)


        connection = connect_database()

        cursor = connection.cursor()


        if text:

            search_value = f"%{text}%"


            cursor.execute("""
                SELECT
                    id,
                    product_code,
                    name,
                    category,
                    brand,
                    model,
                    quantity,
                    minimum_stock,
                    buy_price,
                    sell_price
                FROM products
                WHERE product_code LIKE ?
                   OR name LIKE ?
                   OR category LIKE ?
                   OR brand LIKE ?
                   OR model LIKE ?
                ORDER BY id DESC
            """, (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            ))


        else:

            cursor.execute("""
                SELECT
                    id,
                    product_code,
                    name,
                    category,
                    brand,
                    model,
                    quantity,
                    minimum_stock,
                    buy_price,
                    sell_price
                FROM products
                ORDER BY id DESC
            """)


        products = cursor.fetchall()

        connection.close()


        for product in products:

            quantity = product[6]

            minimum_stock = product[7]


            if quantity == 0:

                status = "ناموجود"

                tag = "empty"

            elif quantity <= minimum_stock:

                status = "موجودی کم"

                tag = "low"

            else:

                status = "موجود"

                tag = "available"


            inventory_tree.insert(
                "",
                "end",
                iid=str(product[0]),
                values=(
                    product[1],
                    product[2],
                    product[3],
                    product[4],
                    product[5],
                    f"{product[6]:,}",
                    f"{product[7]:,}",
                    f"{product[8]:,}",
                    f"{product[9]:,}",
                    status
                ),
                tags=(tag,)
            )


        result_count_var.set(
            f"{len(products):,} کالا"
        )


    # ==================================================
    # BUTTONS
    # ==================================================

    create_action_button(
        action_area,
        "✏️ ویرایش",
        "#EEF2FF",
        PRIMARY,
        edit_product
    )


    create_action_button(
        action_area,
        "🗑️ حذف",
        "#FEF2F2",
        RED,
        delete_product
    )


    create_action_button(
        action_area,
        "🔄 بروزرسانی",
        "#F1F5F9",
        "#475569",
        refresh_inventory
    )


    # ==================================================
    # SEARCH EVENTS
    # ==================================================

    inventory_search_var.trace_add(
        "write",
        search_inventory
    )


    search_entry.bind(
        "<Return>",
        search_inventory
    )


    # ==================================================
    # DOUBLE CLICK EDIT
    # ==================================================

    inventory_tree.bind(
        "<Double-1>",
        lambda event: edit_product()
    )


    # ==================================================
    # INITIAL LOAD
    # ==================================================

    refresh_inventory()


    # ==================================================
    # CLOSE WINDOW
    # ==================================================

    def close_inventory():

        global inventory_window
        global inventory_tree

        inventory_tree = None

        inventory_window.destroy()

        inventory_window = None


    inventory_window.protocol(
        "WM_DELETE_WINDOW",
        close_inventory
    )


# ==================================================
# SEARCH
# ==================================================

def search_product_window():
    if not require_permission("search", window): return

    search_window = tk.Toplevel(window)

    search_window.title("جستجوی کالا")
    search_window.geometry("1250x720")
    search_window.minsize(1050, 650)
    search_window.configure(bg="#F4F6F8")

    # ==================================================
    # HEADER
    # ==================================================

    header = tk.Frame(
        search_window,
        bg="#111827",
        height=105
    )

    header.pack(
        fill="x"
    )

    header.pack_propagate(False)

    icon_label = tk.Label(
        header,
        text="🔍",
        font=("Tahoma", 30),
        bg="#111827",
        fg="white"
    )

    icon_label.pack(
        side="right",
        padx=(20, 35),
        pady=20
    )

    header_text = tk.Frame(
        header,
        bg="#111827"
    )

    header_text.pack(
        side="right",
        pady=18
    )

    title = tk.Label(
        header_text,
        text="جستجوی کالا",
        font=("Tahoma", 20, "bold"),
        bg="#111827",
        fg="white"
    )

    title.pack(
        anchor="e"
    )

    subtitle = tk.Label(
        header_text,
        text="جستجو بر اساس کد، نام، دسته‌بندی، برند یا مدل",
        font=("Tahoma", 10),
        bg="#111827",
        fg="#CBD5E1"
    )

    subtitle.pack(
        anchor="e",
        pady=(4, 0)
    )

    # ==================================================
    # MAIN CONTAINER
    # ==================================================

    main_frame = tk.Frame(
        search_window,
        bg="#F4F6F8"
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=30,
        pady=25
    )

    # ==================================================
    # SEARCH CARD
    # ==================================================

    search_card = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    search_card.pack(
        fill="x",
        pady=(0, 20)
    )

    search_card.columnconfigure(
        0,
        weight=1
    )

    search_var = tk.StringVar()

    search_label = tk.Label(
        search_card,
        text="جستجو",
        font=("Tahoma", 11, "bold"),
        bg="white",
        fg="#374151"
    )

    search_label.grid(
        row=0,
        column=1,
        padx=(15, 25),
        pady=20
    )

    search_entry = tk.Entry(
        search_card,
        textvariable=search_var,
        font=("Tahoma", 12),
        bg="#F9FAFB",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#D1D5DB",
        highlightcolor="#4F46E5",
        justify="right"
    )

    search_entry.grid(
        row=0,
        column=0,
        padx=10,
        pady=18,
        sticky="ew",
        ipady=9
    )

    search_button = tk.Button(
        search_card,
        text="🔍 جستجو",
        font=("Tahoma", 11, "bold"),
        bg="#4F46E5",
        fg="white",
        activebackground="#4338CA",
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        width=13
    )

    search_button.grid(
        row=0,
        column=2,
        padx=(10, 25),
        pady=18,
        ipady=8
    )

    clear_button = tk.Button(
        search_card,
        text="پاک کردن",
        font=("Tahoma", 10, "bold"),
        bg="#E5E7EB",
        fg="#374151",
        activebackground="#D1D5DB",
        activeforeground="#111827",
        relief="flat",
        bd=0,
        cursor="hand2",
        width=10
    )

    clear_button.grid(
        row=0,
        column=3,
        padx=(0, 10),
        pady=18,
        ipady=8
    )

    # ==================================================
    # RESULT HEADER
    # ==================================================

    result_header = tk.Frame(
        main_frame,
        bg="#F4F6F8"
    )

    result_header.pack(
        fill="x",
        pady=(0, 10)
    )

    result_title = tk.Label(
        result_header,
        text="نتایج جستجو",
        font=("Tahoma", 14, "bold"),
        bg="#F4F6F8",
        fg="#111827"
    )

    result_title.pack(
        side="right"
    )

    result_count = tk.Label(
        result_header,
        text="۰ کالا",
        font=("Tahoma", 10),
        bg="#E5E7EB",
        fg="#4B5563",
        padx=12,
        pady=5
    )

    result_count.pack(
        side="left"
    )

    # ==================================================
    # TABLE CARD
    # ==================================================

    table_card = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    table_card.pack(
        fill="both",
        expand=True
    )

    table_frame = tk.Frame(
        table_card,
        bg="white"
    )

    table_frame.pack(
        fill="both",
        expand=True,
        padx=15,
        pady=15
    )

    columns = (
        "product_code",
        "name",
        "category",
        "brand",
        "model",
        "quantity",
        "minimum_stock",
        "buy_price",
        "sell_price",
        "status"
    )

    # ==================================================
    # TREEVIEW STYLE
    # ==================================================

    style = ttk.Style()

    style.configure(
        "Search.Treeview",
        font=("Tahoma", 10),
        rowheight=34,
        background="white",
        fieldbackground="white",
        foreground="#1F2937"
    )

    style.configure(
        "Search.Treeview.Heading",
        font=("Tahoma", 10, "bold"),
        background="#F3F4F6",
        foreground="#111827",
        padding=8
    )

    style.map(
        "Search.Treeview",
        background=[
            ("selected", "#E0E7FF")
        ],
        foreground=[
            ("selected", "#111827")
        ]
    )

    search_tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        style="Search.Treeview",
        selectmode="browse"
    )

    headings = {
        "product_code": "کد کالا",
        "name": "نام کالا",
        "category": "دسته‌بندی",
        "brand": "برند",
        "model": "مدل",
        "quantity": "موجودی",
        "minimum_stock": "حداقل",
        "buy_price": "قیمت خرید",
        "sell_price": "قیمت فروش",
        "status": "وضعیت"
    }

    for column, heading in headings.items():

        search_tree.heading(
            column,
            text=heading
        )

    widths = {
        "product_code": 105,
        "name": 155,
        "category": 115,
        "brand": 105,
        "model": 115,
        "quantity": 80,
        "minimum_stock": 80,
        "buy_price": 120,
        "sell_price": 120,
        "status": 105
    }

    for column, width in widths.items():

        search_tree.column(
            column,
            width=width,
            minwidth=70,
            anchor="center"
        )

    # ==================================================
    # SCROLLBARS
    # ==================================================

    scrollbar_y = ttk.Scrollbar(
        table_frame,
        orient="vertical",
        command=search_tree.yview
    )

    scrollbar_x = ttk.Scrollbar(
        table_frame,
        orient="horizontal",
        command=search_tree.xview
    )

    search_tree.configure(
        yscrollcommand=scrollbar_y.set,
        xscrollcommand=scrollbar_x.set
    )

    search_tree.grid(
        row=0,
        column=0,
        sticky="nsew"
    )

    scrollbar_y.grid(
        row=0,
        column=1,
        sticky="ns"
    )

    scrollbar_x.grid(
        row=1,
        column=0,
        sticky="ew"
    )

    table_frame.rowconfigure(
        0,
        weight=1
    )

    table_frame.columnconfigure(
        0,
        weight=1
    )

    # ==================================================
    # STATUS COLORS
    # ==================================================

    search_tree.tag_configure(
        "available",
        foreground="#15803D"
    )

    search_tree.tag_configure(
        "low",
        foreground="#D97706"
    )

    search_tree.tag_configure(
        "empty",
        foreground="#DC2626"
    )

    # ==================================================
    # FORMAT PRICE
    # ==================================================

    def format_search_price(price):

        return f"{price:,}"

    # ==================================================
    # PERFORM SEARCH
    # ==================================================

    def perform_search(show_message=True):

        text = search_var.get().strip()

        # پاک کردن نتایج قبلی

        for item in search_tree.get_children():

            search_tree.delete(item)

        connection = connect_database()
        cursor = connection.cursor()

        if text:

            search_value = f"%{text}%"

            cursor.execute("""
                SELECT
                    id,
                    product_code,
                    name,
                    category,
                    brand,
                    model,
                    quantity,
                    minimum_stock,
                    buy_price,
                    sell_price
                FROM products
                WHERE product_code LIKE ?
                   OR name LIKE ?
                   OR category LIKE ?
                   OR brand LIKE ?
                   OR model LIKE ?
                ORDER BY id DESC
            """, (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            ))

        else:

            cursor.execute("""
                SELECT
                    id,
                    product_code,
                    name,
                    category,
                    brand,
                    model,
                    quantity,
                    minimum_stock,
                    buy_price,
                    sell_price
                FROM products
                ORDER BY id DESC
            """)

        products = cursor.fetchall()

        connection.close()

        # ==================================================
        # INSERT RESULTS
        # ==================================================

        for product in products:

            quantity = product[6]
            minimum_stock = product[7]

            if quantity == 0:

                status = "ناموجود"
                tag = "empty"

            elif quantity <= minimum_stock:

                status = "موجودی کم"
                tag = "low"

            else:

                status = "موجود"
                tag = "available"

            search_tree.insert(
                "",
                "end",
                iid=str(product[0]),
                values=(
                    product[1],
                    product[2],
                    product[3],
                    product[4],
                    product[5],
                    product[6],
                    product[7],
                    format_search_price(product[8]),
                    format_search_price(product[9]),
                    status
                ),
                tags=(tag,)
            )

        # ==================================================
        # RESULT COUNT
        # ==================================================

        result_count.config(
            text=f"{len(products):,} کالا"
        )

        if not products and text and show_message:

            messagebox.showinfo(
                "نتیجه جستجو",
                "هیچ کالایی مطابق عبارت جستجو پیدا نشد.",
                parent=search_window
            )

    # ==================================================
    # CLEAR SEARCH
    # ==================================================

    def clear_search():

        search_var.set("")

        for item in search_tree.get_children():

            search_tree.delete(item)

        result_count.config(
            text="۰ کالا"
        )

        search_entry.focus()

    # ==================================================
    # BUTTON COMMANDS
    # ==================================================

    search_button.config(
        command=perform_search
    )

    clear_button.config(
        command=clear_search
    )

    # ==================================================
    # KEYBOARD
    # ==================================================

    search_entry.bind(
        "<Return>",
        lambda event: perform_search()
    )

    search_window.bind(
        "<Escape>",
        lambda event: search_window.destroy()
    )

    # ==================================================
    # DOUBLE CLICK
    # ==================================================

    def show_selected_product(event):

        selected = search_tree.selection()

        if not selected:
            return

        product_id = selected[0]

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                product_code,
                name,
                category,
                brand,
                model,
                quantity,
                minimum_stock,
                buy_price,
                sell_price
            FROM products
            WHERE id = ?
        """, (product_id,))

        product = cursor.fetchone()

        connection.close()

        if product is None:
            return

        messagebox.showinfo(
            "جزئیات کالا",
            (
                f"کد کالا: {product[0]}\n"
                f"نام: {product[1]}\n"
                f"دسته‌بندی: {product[2]}\n"
                f"برند: {product[3]}\n"
                f"مدل: {product[4]}\n\n"
                f"موجودی: {product[5]}\n"
                f"حداقل موجودی: {product[6]}\n\n"
                f"قیمت خرید: {product[7]:,} تومان\n"
                f"قیمت فروش: {product[8]:,} تومان"
            ),
            parent=search_window
        )

    search_tree.bind(
        "<Double-1>",
        show_selected_product
    )

    # ==================================================
    # INITIAL LOAD
    # ==================================================

    perform_search(
        show_message=False
    )

    search_entry.focus()


# ==================================================
# STOCK MOVEMENT
# ==================================================

def get_products_for_combobox():

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            product_code,
            name,
            brand,
            model,
            quantity,
            sell_price
        FROM products
        ORDER BY name
    """)

    products = cursor.fetchall()

    connection.close()

    return products


# ==================================================
# STOCK MOVEMENT
# ==================================================

def stock_movement_window(movement_type):
    if not require_permission("stock", window): return

    movement_window = tk.Toplevel(window)

    if movement_type == "ورود":

        title_text = "📥 ورود کالا"
        header_color = "#166534"
        button_color = "#16A34A"
        active_color = "#15803D"
        operation_text = "افزایش موجودی کالا"

    else:

        title_text = "📤 خروج کالا"
        header_color = "#991B1B"
        button_color = "#DC2626"
        active_color = "#B91C1C"
        operation_text = "کاهش موجودی کالا"

    movement_window.title(title_text)
    movement_window.geometry("650x560")
    movement_window.minsize(600, 520)
    movement_window.configure(bg="#F4F6F8")

    # ==================================================
    # HEADER
    # ==================================================

    header = tk.Frame(
        movement_window,
        bg=header_color,
        height=115
    )

    header.pack(fill="x")
    header.pack_propagate(False)

    icon_label = tk.Label(
        header,
        text="📥" if movement_type == "ورود" else "📤",
        font=("Tahoma", 32),
        bg=header_color,
        fg="white"
    )

    icon_label.pack(
        side="right",
        padx=(20, 35),
        pady=25
    )

    header_text = tk.Frame(
        header,
        bg=header_color
    )

    header_text.pack(
        side="right",
        pady=20
    )

    title_label = tk.Label(
        header_text,
        text=title_text,
        font=("Tahoma", 20, "bold"),
        bg=header_color,
        fg="white"
    )

    title_label.pack(anchor="e")

    subtitle_label = tk.Label(
        header_text,
        text=operation_text,
        font=("Tahoma", 10),
        bg=header_color,
        fg="#DCFCE7" if movement_type == "ورود" else "#FECACA"
    )

    subtitle_label.pack(
        anchor="e",
        pady=(5, 0)
    )

    # ==================================================
    # MAIN
    # ==================================================

    main_frame = tk.Frame(
        movement_window,
        bg="#F4F6F8"
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=35,
        pady=25
    )

    # ==================================================
    # FORM CARD
    # ==================================================

    form_card = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    form_card.pack(
        fill="both",
        expand=True
    )

    form_card.columnconfigure(
        0,
        weight=1
    )

    # ==================================================
    # CARD TITLE
    # ==================================================

    card_title = tk.Label(
        form_card,
        text="ثبت عملیات موجودی",
        font=("Tahoma", 14, "bold"),
        bg="white",
        fg="#111827"
    )

    card_title.grid(
        row=0,
        column=0,
        padx=30,
        pady=(25, 5),
        sticky="e"
    )

    card_description = tk.Label(
        form_card,
        text="کالا و تعداد مورد نظر را انتخاب کنید",
        font=("Tahoma", 10),
        bg="white",
        fg="#6B7280"
    )

    card_description.grid(
        row=1,
        column=0,
        padx=30,
        pady=(0, 18),
        sticky="e"
    )

    separator = tk.Frame(
        form_card,
        bg="#E5E7EB",
        height=1
    )

    separator.grid(
        row=2,
        column=0,
        sticky="ew",
        padx=30
    )

    # ==================================================
    # LOAD PRODUCTS
    # ==================================================

    products = get_products_for_combobox()

    product_values = []
    product_dictionary = {}

    for product in products:

        display_text = (
            f"{product[1]}  |  "
            f"{product[2]}  |  "
            f"{product[3]}  |  "
            f"{product[4]}  |  "
            f"موجودی: {product[5]:,}"
        )

        product_values.append(
            display_text
        )

        product_dictionary[
            display_text
        ] = product

    # ==================================================
    # PRODUCT
    # ==================================================

    product_label = tk.Label(
        form_card,
        text="انتخاب کالا",
        font=("Tahoma", 11, "bold"),
        bg="white",
        fg="#374151"
    )

    product_label.grid(
        row=3,
        column=0,
        padx=30,
        pady=(22, 7),
        sticky="e"
    )

    product_combo = ttk.Combobox(
        form_card,
        values=product_values,
        state="readonly",
        font=("Tahoma", 10),
        justify="right"
    )

    product_combo.grid(
        row=4,
        column=0,
        padx=30,
        pady=(0, 15),
        sticky="ew",
        ipady=7
    )

    # ==================================================
    # CURRENT STOCK
    # ==================================================

    current_stock_var = tk.StringVar(
        value="موجودی فعلی: -"
    )

    current_stock_label = tk.Label(
        form_card,
        textvariable=current_stock_var,
        font=("Tahoma", 10, "bold"),
        bg="#F9FAFB",
        fg="#4B5563",
        padx=15,
        pady=8
    )

    current_stock_label.grid(
        row=5,
        column=0,
        padx=30,
        pady=(0, 15),
        sticky="e"
    )

    # ==================================================
    # QUANTITY
    # ==================================================

    quantity_label = tk.Label(
        form_card,
        text="تعداد",
        font=("Tahoma", 11, "bold"),
        bg="white",
        fg="#374151"
    )

    quantity_label.grid(
        row=6,
        column=0,
        padx=30,
        pady=(5, 7),
        sticky="e"
    )

    quantity_var = tk.StringVar()

    quantity_entry = tk.Entry(
        form_card,
        textvariable=quantity_var,
        font=("Tahoma", 12),
        bg="#F9FAFB",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#D1D5DB",
        highlightcolor=button_color,
        justify="right"
    )

    quantity_entry.grid(
        row=7,
        column=0,
        padx=30,
        pady=(0, 20),
        sticky="ew",
        ipady=9
    )

    # ==================================================
    # UPDATE STOCK DISPLAY
    # ==================================================

    def update_current_stock(event=None):

        selected = product_combo.get().strip()

        if not selected:

            current_stock_var.set(
                "موجودی فعلی: -"
            )

            return

        product = product_dictionary.get(
            selected
        )

        if product:

            current_stock_var.set(
                f"موجودی فعلی: {product[5]:,} عدد"
            )

    product_combo.bind(
        "<<ComboboxSelected>>",
        update_current_stock
    )

    # ==================================================
    # SAVE MOVEMENT
    # ==================================================

    def save_movement():

        selected = product_combo.get().strip()

        if not selected:

            messagebox.showerror(
                "انتخاب کالا",
                "لطفاً ابتدا یک کالا انتخاب کنید.",
                parent=movement_window
            )

            product_combo.focus()
            return

        try:

            amount = int(
                quantity_var.get().strip()
            )

        except ValueError:

            messagebox.showerror(
                "خطای اطلاعات",
                "تعداد باید به صورت عدد وارد شود.",
                parent=movement_window
            )

            quantity_entry.focus()
            return

        if amount <= 0:

            messagebox.showerror(
                "خطای اطلاعات",
                "تعداد باید بیشتر از صفر باشد.",
                parent=movement_window
            )

            quantity_entry.focus()
            return

        product = product_dictionary.get(
            selected
        )

        if product is None:

            messagebox.showerror(
                "خطا",
                "کالای انتخاب‌شده پیدا نشد.",
                parent=movement_window
            )

            return

        product_id = product[0]
        product_name = product[2]
        current_quantity = product[5]

        # ==================================================
        # CALCULATE NEW STOCK
        # ==================================================

        if movement_type == "ورود":

            new_quantity = (
                current_quantity + amount
            )

        else:

            if amount > current_quantity:

                messagebox.showerror(
                    "موجودی کافی نیست",
                    (
                        f"موجودی فعلی کالای «{product_name}» "
                        f"{current_quantity:,} عدد است.\n\n"
                        f"تعداد خروج نمی‌تواند بیشتر از موجودی باشد."
                    ),
                    parent=movement_window
                )

                quantity_entry.focus()
                return

            new_quantity = (
                current_quantity - amount
            )

        # ==================================================
        # CONFIRM
        # ==================================================

        confirmation = messagebox.askyesno(
            "تأیید عملیات",
            (
                f"آیا عملیات زیر ثبت شود؟\n\n"
                f"کالا: {product_name}\n"
                f"نوع عملیات: {movement_type}\n"
                f"تعداد: {amount:,}\n"
                f"موجودی فعلی: {current_quantity:,}\n"
                f"موجودی جدید: {new_quantity:,}"
            ),
            parent=movement_window
        )

        if not confirmation:
            return

        # ==================================================
        # DATABASE
        # ==================================================

        connection = connect_database()
        cursor = connection.cursor()

        try:

            # -----------------------------
            # Update product quantity
            # -----------------------------

            cursor.execute("""
                UPDATE products
                SET quantity = ?
                WHERE id = ?
            """, (
                new_quantity,
                product_id
            ))

            # -----------------------------
            # Save movement history
            # -----------------------------

            cursor.execute("""
                INSERT INTO stock_movements
                (
                    product_id,
                    movement_type,
                    quantity,
                    date
                )
                VALUES (?, ?, ?, ?)
            """, (
                product_id,
                movement_type,
                amount,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

            connection.commit()

        except Exception as error:

            connection.rollback()

            messagebox.showerror(
                "خطا",
                f"ثبت عملیات انجام نشد.\n\n{error}",
                parent=movement_window
            )

            return

        finally:

            connection.close()

        # ==================================================
        # SUCCESS
        # ==================================================

        messagebox.showinfo(
            "ثبت موفق",
            (
                f"عملیات «{movement_type}» با موفقیت ثبت شد.\n\n"
                f"کالا: {product_name}\n"
                f"تعداد: {amount:,}\n"
                f"موجودی جدید: {new_quantity:,}"
            ),
            parent=movement_window
        )

        # ==================================================
        # REFRESH INVENTORY WINDOW
        # ==================================================

        if inventory_window_exists():

            try:
                load_products()
            except Exception:
                pass

        movement_window.destroy()

    # ==================================================
    # BUTTON AREA
    # ==================================================

    button_frame = tk.Frame(
        form_card,
        bg="white"
    )

    button_frame.grid(
        row=8,
        column=0,
        sticky="ew",
        padx=30,
        pady=(0, 25)
    )

    save_button = tk.Button(
        button_frame,
        text="✓ ثبت عملیات",
        font=("Tahoma", 12, "bold"),
        bg=button_color,
        fg="white",
        activebackground=active_color,
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=save_movement
    )

    save_button.pack(
        side="right",
        fill="x",
        expand=True,
        padx=(5, 0),
        ipady=9
    )

    cancel_button = tk.Button(
        button_frame,
        text="انصراف",
        font=("Tahoma", 11, "bold"),
        bg="#E5E7EB",
        fg="#374151",
        activebackground="#D1D5DB",
        activeforeground="#111827",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=movement_window.destroy
    )

    cancel_button.pack(
        side="left",
        fill="x",
        expand=True,
        padx=(0, 5),
        ipady=9
    )

    # ==================================================
    # KEYBOARD
    # ==================================================

    movement_window.bind(
        "<Return>",
        lambda event: save_movement()
    )

    movement_window.bind(
        "<Escape>",
        lambda event: movement_window.destroy()
    )

    product_combo.focus()

# ==================================================
# SALES
# ==================================================

def get_customers_for_combobox():

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            phone
        FROM customers
        ORDER BY name
    """)

    customers = cursor.fetchall()

    connection.close()

    return customers


# ==================================================
# HISTORY
# ==================================================

def history_window():
    if not require_permission("history", window): return

    history_win = tk.Toplevel(window)

    history_win.title("تاریخچه ورود و خروج")
    history_win.geometry("1050x650")
    history_win.minsize(900, 550)

    history_win.configure(bg="#F4F6F8")

    # --------------------------------------------------
    # HEADER
    # --------------------------------------------------

    header_frame = tk.Frame(
        history_win,
        bg="#FFFFFF"
    )

    header_frame.pack(
        fill="x",
        padx=25,
        pady=(25, 15)
    )

    title = tk.Label(
        header_frame,
        text="📋 تاریخچه ورود و خروج کالا",
        font=("Tahoma", 22, "bold"),
        bg="#FFFFFF",
        fg="#1F2937"
    )

    title.pack(
        pady=(18, 5)
    )

    subtitle = tk.Label(
        header_frame,
        text="سوابق تمام عملیات ثبت‌شده در انبار",
        font=("Tahoma", 11),
        bg="#FFFFFF",
        fg="#6B7280"
    )

    subtitle.pack(
        pady=(0, 18)
    )

    # --------------------------------------------------
    # TABLE CONTAINER
    # --------------------------------------------------

    table_container = tk.Frame(
        history_win,
        bg="#FFFFFF",
        bd=0
    )

    table_container.pack(
        fill="both",
        expand=True,
        padx=25,
        pady=10
    )

    table_frame = tk.Frame(
        table_container,
        bg="#FFFFFF"
    )

    table_frame.pack(
        fill="both",
        expand=True,
        padx=15,
        pady=15
    )

    columns = (
        "code",
        "name",
        "movement",
        "quantity",
        "date"
    )

    tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        height=15
    )

    # --------------------------------------------------
    # TABLE HEADERS
    # --------------------------------------------------

    tree.heading(
        "code",
        text="کد کالا"
    )

    tree.heading(
        "name",
        text="نام کالا"
    )

    tree.heading(
        "movement",
        text="نوع عملیات"
    )

    tree.heading(
        "quantity",
        text="تعداد"
    )

    tree.heading(
        "date",
        text="تاریخ و ساعت"
    )

    # --------------------------------------------------
    # TABLE COLUMNS
    # --------------------------------------------------

    tree.column(
        "code",
        width=130,
        anchor="center"
    )

    tree.column(
        "name",
        width=250,
        anchor="center"
    )

    tree.column(
        "movement",
        width=150,
        anchor="center"
    )

    tree.column(
        "quantity",
        width=100,
        anchor="center"
    )

    tree.column(
        "date",
        width=220,
        anchor="center"
    )

    # --------------------------------------------------
    # SCROLLBAR
    # --------------------------------------------------

    scrollbar = ttk.Scrollbar(
        table_frame,
        orient="vertical",
        command=tree.yview
    )

    tree.configure(
        yscrollcommand=scrollbar.set
    )

    tree.pack(
        side="left",
        fill="both",
        expand=True
    )

    scrollbar.pack(
        side="right",
        fill="y"
    )

    # --------------------------------------------------
    # LOAD HISTORY
    # --------------------------------------------------

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            products.product_code,
            products.name,
            stock_movements.movement_type,
            stock_movements.quantity,
            stock_movements.date
        FROM stock_movements
        INNER JOIN products
        ON stock_movements.product_id = products.id
        ORDER BY stock_movements.id DESC
    """)

    movements = cursor.fetchall()

    connection.close()

    # --------------------------------------------------
    # INSERT DATA
    # --------------------------------------------------

    for movement in movements:

        tree.insert(
            "",
            "end",
            values=(
                movement[0],
                movement[1],
                movement[2],
                movement[3],
                movement[4]
            )
        )

    # --------------------------------------------------
    # FOOTER
    # --------------------------------------------------

    footer_frame = tk.Frame(
        history_win,
        bg="#F4F6F8"
    )

    footer_frame.pack(
        fill="x",
        padx=25,
        pady=(5, 20)
    )

    count_label = tk.Label(
        footer_frame,
        text=f"تعداد عملیات ثبت‌شده: {len(movements)}",
        font=("Tahoma", 10, "bold"),
        bg="#F4F6F8",
        fg="#6B7280"
    )

    count_label.pack(
        side="right",
        padx=10
    )

    close_button = tk.Button(
        footer_frame,
        text="بستن",
        font=("Tahoma", 11, "bold"),
        width=12,
        height=1,
        bg="#E5E7EB",
        fg="#1F2937",
        activebackground="#D1D5DB",
        activeforeground="#111827",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=history_win.destroy
    )

    close_button.pack(
        side="left",
        padx=10
    )


# ==================================================
# DASHBOARD - PROFESSIONAL VERSION
# ==================================================

def dashboard_window():
    if not require_permission("dashboard", window): return

    dashboard_win = tk.Toplevel(window)

    dashboard_win.title(
        "داشبورد مدیریت فروشگاه"
    )

    dashboard_win.geometry(
        "1250x820"
    )

    dashboard_win.minsize(
        1050,
        700
    )

    dashboard_win.configure(
        bg="#F4F6F8"
    )

    # ==================================================
    # HEADER
    # ==================================================

    header_frame = tk.Frame(
        dashboard_win,
        bg="#1F2937",
        height=90
    )

    header_frame.pack(
        fill="x"
    )

    header_frame.pack_propagate(False)

    title = tk.Label(
        header_frame,
        text="📊 داشبورد مدیریت فروشگاه",
        font=("Tahoma", 24, "bold"),
        bg="#1F2937",
        fg="white"
    )

    title.pack(
        side="right",
        padx=30
    )

    subtitle = tk.Label(
        header_frame,
        text="مرکز کنترل و بررسی وضعیت موجودی",
        font=("Tahoma", 11),
        bg="#1F2937",
        fg="#D1D5DB"
    )

    subtitle.pack(
        side="right",
        padx=5
    )

    # ==================================================
    # MAIN CONTAINER
    # ==================================================

    main_frame = tk.Frame(
        dashboard_win,
        bg="#F4F6F8"
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=25,
        pady=20
    )

    # ==================================================
    # TOP STATISTICS
    # ==================================================

    stats_frame = tk.Frame(
        main_frame,
        bg="#F4F6F8"
    )

    stats_frame.pack(
        fill="x",
        pady=(0, 15)
    )

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM products
    """)

    total_products = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(quantity), 0)
        FROM products
    """)

    total_quantity = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE quantity = 0
    """)

    out_of_stock = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE quantity > 0
        AND quantity <= minimum_stock
    """)

    low_stock = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(
            SUM(quantity * buy_price),
            0
        )
        FROM products
    """)

    buy_value = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(
            SUM(quantity * sell_price),
            0
        )
        FROM products
    """)

    sell_value = cursor.fetchone()[0]

    connection.close()

    potential_profit = sell_value - buy_value

    create_dashboard_card(
        stats_frame,
        "📦",
        "تعداد کالاها",
        f"{total_products:,}",
        "#E8F0FE",
        0
    )

    create_dashboard_card(
        stats_frame,
        "🔢",
        "مجموع موجودی",
        f"{total_quantity:,}",
        "#E8F5E9",
        1
    )

    create_dashboard_card(
        stats_frame,
        "⚠️",
        "موجودی کم",
        f"{low_stock:,}",
        "#FFF7E6",
        2
    )

    create_dashboard_card(
        stats_frame,
        "❌",
        "ناموجود",
        f"{out_of_stock:,}",
        "#FDECEC",
        3
    )

    # ==================================================
    # FINANCIAL CARDS
    # ==================================================

    financial_frame = tk.Frame(
        main_frame,
        bg="#F4F6F8"
    )

    financial_frame.pack(
        fill="x",
        pady=(0, 20)
    )

    create_dashboard_card(
        financial_frame,
        "💰",
        "ارزش خرید موجودی",
        format_price(buy_value),
        "#F3E8FF",
        0
    )

    create_dashboard_card(
        financial_frame,
        "💵",
        "ارزش فروش موجودی",
        format_price(sell_value),
        "#E0F2FE",
        1
    )

    create_dashboard_card(
        financial_frame,
        "📈",
        "سود بالقوه موجودی",
        format_price(potential_profit),
        "#DCFCE7",
        2
    )

    # ==================================================
    # PERIODIC PERFORMANCE
    # ==================================================

    performance_frame = tk.Frame(
        main_frame,
        bg="white",
        bd=0,
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    performance_frame.pack(
        fill="x",
        pady=(0, 20)
    )

    performance_header = tk.Frame(
        performance_frame,
        bg="white"
    )

    performance_header.pack(
        fill="x",
        padx=20,
        pady=(15, 5)
    )

    performance_title = tk.Label(
        performance_header,
        text="📅 عملکرد دوره‌ای",
        font=("Tahoma", 17, "bold"),
        bg="white",
        fg="#1F2937"
    )

    performance_title.pack(
        side="right"
    )

    period_var = tk.StringVar(
        value="۳۰ روز اخیر"
    )

    period_combo = ttk.Combobox(
        performance_header,
        textvariable=period_var,
        values=[
            "امروز",
            "۷ روز اخیر",
            "۳۰ روز اخیر",
            "۹۰ روز اخیر",
            "۱ سال اخیر",
            "بازه دلخواه"
        ],
        state="readonly",
        font=("Tahoma", 11),
        width=18
    )

    period_combo.pack(
        side="left",
        padx=10
    )

    custom_frame = tk.Frame(
        performance_frame,
        bg="white"
    )

    custom_frame.pack(
        fill="x",
        padx=20,
        pady=5
    )

    start_var = tk.StringVar()
    end_var = tk.StringVar()

    start_label = tk.Label(
        custom_frame,
        text="از:",
        font=("Tahoma", 10),
        bg="white"
    )

    start_entry = tk.Entry(
        custom_frame,
        textvariable=start_var,
        font=("Tahoma", 10),
        width=14,
        justify="center"
    )

    end_label = tk.Label(
        custom_frame,
        text="تا:",
        font=("Tahoma", 10),
        bg="white"
    )

    end_entry = tk.Entry(
        custom_frame,
        textvariable=end_var,
        font=("Tahoma", 10),
        width=14,
        justify="center"
    )

    # ==================================================
    # PERFORMANCE DATA
    # ==================================================

    performance_cards = tk.Frame(
        performance_frame,
        bg="white"
    )

    performance_cards.pack(
        fill="x",
        padx=20,
        pady=10
    )

    entry_count_var = tk.StringVar(value="0")
    entry_quantity_var = tk.StringVar(value="0")
    exit_count_var = tk.StringVar(value="0")
    exit_quantity_var = tk.StringVar(value="0")
    sales_value_var = tk.StringVar(value="0 تومان")
    purchase_value_var = tk.StringVar(value="0 تومان")
    profit_var = tk.StringVar(value="0 تومان")

    def create_performance_box(
        parent,
        title,
        value_var,
        icon,
        column
    ):

        box = tk.Frame(
            parent,
            bg="#F8FAFC",
            highlightthickness=1,
            highlightbackground="#E5E7EB"
        )

        box.grid(
            row=0,
            column=column,
            padx=5,
            sticky="nsew"
        )

        parent.grid_columnconfigure(
            column,
            weight=1
        )

        icon_label = tk.Label(
            box,
            text=icon,
            font=("Tahoma", 18),
            bg="#F8FAFC"
        )

        icon_label.pack(
            pady=(10, 0)
        )

        title_label = tk.Label(
            box,
            text=title,
            font=("Tahoma", 9),
            bg="#F8FAFC",
            fg="#6B7280"
        )

        title_label.pack()

        value_label = tk.Label(
            box,
            textvariable=value_var,
            font=("Tahoma", 12, "bold"),
            bg="#F8FAFC",
            fg="#111827"
        )

        value_label.pack(
            pady=(3, 12)
        )

    create_performance_box(
        performance_cards,
        "تعداد ورود",
        entry_count_var,
        "📥",
        0
    )

    create_performance_box(
        performance_cards,
        "تعداد کالای واردشده",
        entry_quantity_var,
        "📦",
        1
    )

    create_performance_box(
        performance_cards,
        "تعداد خروج",
        exit_count_var,
        "📤",
        2
    )

    create_performance_box(
        performance_cards,
        "تعداد کالای خارج‌شده",
        exit_quantity_var,
        "📦",
        3
    )

    create_performance_box(
        performance_cards,
        "ارزش فروش خروجی",
        sales_value_var,
        "💵",
        4
    )

    create_performance_box(
        performance_cards,
        "سود تقریبی",
        profit_var,
        "📈",
        5
    )

    # ==================================================
    # CHART
    # ==================================================

    chart_title = tk.Label(
        performance_frame,
        text="📊 نمودار ورود و خروج",
        font=("Tahoma", 12, "bold"),
        bg="white",
        fg="#374151"
    )

    chart_title.pack(
        anchor="e",
        padx=25,
        pady=(5, 5)
    )

    chart_canvas = tk.Canvas(
        performance_frame,
        height=180,
        bg="white",
        highlightthickness=0
    )

    chart_canvas.pack(
        fill="x",
        padx=20,
        pady=(0, 15)
    )

    # ==================================================
    # PERIOD CALCULATION
    # ==================================================

    def get_period():

        today = datetime.now()

        selected = period_var.get()

        if selected == "امروز":

            start_date = today.strftime(
                "%Y-%m-%d"
            )

            end_date = start_date

        elif selected == "۷ روز اخیر":

            from datetime import timedelta

            start_date = (
                today - timedelta(days=6)
            ).strftime("%Y-%m-%d")

            end_date = today.strftime(
                "%Y-%m-%d"
            )

        elif selected == "۳۰ روز اخیر":

            from datetime import timedelta

            start_date = (
                today - timedelta(days=29)
            ).strftime("%Y-%m-%d")

            end_date = today.strftime(
                "%Y-%m-%d"
            )

        elif selected == "۹۰ روز اخیر":

            from datetime import timedelta

            start_date = (
                today - timedelta(days=89)
            ).strftime("%Y-%m-%d")

            end_date = today.strftime(
                "%Y-%m-%d"
            )

        elif selected == "۱ سال اخیر":

            from datetime import timedelta

            start_date = (
                today - timedelta(days=364)
            ).strftime("%Y-%m-%d")

            end_date = today.strftime(
                "%Y-%m-%d"
            )

        else:

            start_date = start_var.get().strip()
            end_date = end_var.get().strip()

            if not start_date or not end_date:

                messagebox.showwarning(
                    "بازه دلخواه",
                    "تاریخ شروع و پایان را وارد کنید.\n\n"
                    "فرمت تاریخ:\n"
                    "YYYY-MM-DD",
                    parent=dashboard_win
                )

                return None

        return start_date, end_date

    # ==================================================
    # DRAW CHART
    # ==================================================

    def draw_chart(
        start_date,
        end_date
    ):

        chart_canvas.delete("all")

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                substr(date, 1, 10) AS day,
                SUM(
                    CASE
                        WHEN movement_type = 'ورود'
                        OR movement_type = 'ورود اولیه'
                        THEN quantity
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN movement_type = 'خروج'
                        THEN quantity
                        ELSE 0
                    END
                )
            FROM stock_movements
            WHERE substr(date, 1, 10)
                  BETWEEN ? AND ?
            GROUP BY substr(date, 1, 10)
            ORDER BY day
        """, (
            start_date,
            end_date
        ))

        chart_data = cursor.fetchall()

        connection.close()

        width = chart_canvas.winfo_width()

        if width < 100:
            width = 900

        height = 180

        left = 45
        right = width - 25
        top = 20
        bottom = height - 35

        # محور‌ها

        chart_canvas.create_line(
            left,
            top,
            left,
            bottom,
            fill="#CBD5E1"
        )

        chart_canvas.create_line(
            left,
            bottom,
            right,
            bottom,
            fill="#CBD5E1"
        )

        if not chart_data:

            chart_canvas.create_text(
                width / 2,
                height / 2,
                text="در این بازه اطلاعاتی ثبت نشده است",
                font=("Tahoma", 11),
                fill="#9CA3AF"
            )

            return

        max_value = max(
            max(row[1] or 0, row[2] or 0)
            for row in chart_data
        )

        if max_value == 0:
            max_value = 1

        chart_width = right - left
        chart_height = bottom - top

        count = len(chart_data)

        if count == 1:
            step_x = 0
        else:
            step_x = chart_width / (count - 1)

        previous_entry = None
        previous_exit = None

        for index, row in enumerate(chart_data):

            day = row[0]
            entry_value = row[1] or 0
            exit_value = row[2] or 0

            if count == 1:
                x = left + chart_width / 2
            else:
                x = left + index * step_x

            entry_y = (
                bottom -
                (entry_value / max_value)
                * chart_height
            )

            exit_y = (
                bottom -
                (exit_value / max_value)
                * chart_height
            )

            if previous_entry is not None:

                chart_canvas.create_line(
                    previous_entry[0],
                    previous_entry[1],
                    x,
                    entry_y,
                    fill="#16A34A",
                    width=3
                )

            if previous_exit is not None:

                chart_canvas.create_line(
                    previous_exit[0],
                    previous_exit[1],
                    x,
                    exit_y,
                    fill="#DC2626",
                    width=3
                )

            chart_canvas.create_oval(
                x - 3,
                entry_y - 3,
                x + 3,
                entry_y + 3,
                fill="#16A34A",
                outline=""
            )

            chart_canvas.create_oval(
                x - 3,
                exit_y - 3,
                x + 3,
                exit_y + 3,
                fill="#DC2626",
                outline=""
            )

            if index == 0 or index == count - 1:

                chart_canvas.create_text(
                    x,
                    bottom + 15,
                    text=day,
                    font=("Tahoma", 8),
                    fill="#6B7280"
                )

            previous_entry = (
                x,
                entry_y
            )

            previous_exit = (
                x,
                exit_y
            )

        # راهنمای نمودار

        chart_canvas.create_line(
            right - 150,
            top,
            right - 125,
            top,
            fill="#16A34A",
            width=3
        )

        chart_canvas.create_text(
            right - 115,
            top,
            text="ورود",
            anchor="w",
            font=("Tahoma", 9),
            fill="#374151"
        )

        chart_canvas.create_line(
            right - 65,
            top,
            right - 40,
            top,
            fill="#DC2626",
            width=3
        )

        chart_canvas.create_text(
            right - 35,
            top,
            text="خروج",
            anchor="w",
            font=("Tahoma", 9),
            fill="#374151"
        )

    # ==================================================
    # LOAD PERFORMANCE
    # ==================================================

    def load_performance():

        period = get_period()

        if period is None:
            return

        start_date, end_date = period

        connection = connect_database()
        cursor = connection.cursor()

        # ----------------------------------------------
        # تعداد ورود و خروج
        # ----------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(
                    CASE
                        WHEN movement_type = 'ورود'
                        OR movement_type = 'ورود اولیه'
                        THEN 1
                    END
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN movement_type = 'ورود'
                            OR movement_type = 'ورود اولیه'
                            THEN quantity
                            ELSE 0
                        END
                    ),
                    0
                ),
                COUNT(
                    CASE
                        WHEN movement_type = 'خروج'
                        THEN 1
                    END
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN movement_type = 'خروج'
                            THEN quantity
                            ELSE 0
                        END
                    ),
                    0
                )
            FROM stock_movements
            WHERE substr(date, 1, 10)
                  BETWEEN ? AND ?
        """, (
            start_date,
            end_date
        ))

        result = cursor.fetchone()

        entry_count = result[0] or 0
        entry_quantity = result[1] or 0
        exit_count = result[2] or 0
        exit_quantity = result[3] or 0

        # ----------------------------------------------
        # ارزش خروج
        # ----------------------------------------------

        cursor.execute("""
            SELECT COALESCE(
                SUM(
                    sm.quantity *
                    p.sell_price
                ),
                0
            )
            FROM stock_movements sm
            INNER JOIN products p
            ON sm.product_id = p.id
            WHERE sm.movement_type = 'خروج'
            AND substr(sm.date, 1, 10)
                BETWEEN ? AND ?
        """, (
            start_date,
            end_date
        ))

        sales_value = cursor.fetchone()[0] or 0

        # ----------------------------------------------
        # ارزش خرید خروج
        # ----------------------------------------------

        cursor.execute("""
            SELECT COALESCE(
                SUM(
                    sm.quantity *
                    p.buy_price
                ),
                0
            )
            FROM stock_movements sm
            INNER JOIN products p
            ON sm.product_id = p.id
            WHERE sm.movement_type = 'خروج'
            AND substr(sm.date, 1, 10)
                BETWEEN ? AND ?
        """, (
            start_date,
            end_date
        ))

        purchase_value = cursor.fetchone()[0] or 0

        connection.close()

        profit = (
            sales_value -
            purchase_value
        )

        entry_count_var.set(
            f"{entry_count:,}"
        )

        entry_quantity_var.set(
            f"{entry_quantity:,}"
        )

        exit_count_var.set(
            f"{exit_count:,}"
        )

        exit_quantity_var.set(
            f"{exit_quantity:,}"
        )

        sales_value_var.set(
            format_price(sales_value)
        )

        purchase_value_var.set(
            format_price(purchase_value)
        )

        profit_var.set(
            format_price(profit)
        )

        draw_chart(
            start_date,
            end_date
        )

    # ==================================================
    # CUSTOM DATE VISIBILITY
    # ==================================================

    def update_custom_date_fields(event=None):

        if period_var.get() == "بازه دلخواه":

            start_label.pack(
                side="right",
                padx=5
            )

            start_entry.pack(
                side="right",
                padx=5
            )

            end_label.pack(
                side="right",
                padx=5
            )

            end_entry.pack(
                side="right",
                padx=5
            )

        else:

            start_label.pack_forget()
            start_entry.pack_forget()
            end_label.pack_forget()
            end_entry.pack_forget()

            load_performance()

    period_combo.bind(
        "<<ComboboxSelected>>",
        update_custom_date_fields
    )

    # ==================================================
    # UPDATE BUTTON
    # ==================================================

    update_button = tk.Button(
        performance_header,
        text="🔄 بروزرسانی",
        font=("Tahoma", 10, "bold"),
        bg="#2563EB",
        fg="white",
        activebackground="#1D4ED8",
        activeforeground="white",
        relief="flat",
        bd=0,
        padx=15,
        pady=7,
        cursor="hand2",
        command=load_performance
    )

    update_button.pack(
        side="left"
    )

    # ==================================================
    # LOW STOCK SECTION
    # ==================================================

    attention_frame = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    attention_frame.pack(
        fill="both",
        expand=True
    )

    attention_title = tk.Label(
        attention_frame,
        text="⚠️ کالاهای نیازمند توجه",
        font=("Tahoma", 16, "bold"),
        bg="white",
        fg="#1F2937"
    )

    attention_title.pack(
        anchor="e",
        padx=20,
        pady=15
    )

    table_frame = tk.Frame(
        attention_frame,
        bg="white"
    )

    table_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=(0, 15)
    )

    columns = (
        "code",
        "name",
        "brand",
        "model",
        "quantity",
        "minimum",
        "status"
    )

    tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        height=7
    )

    headings = {
        "code": "کد کالا",
        "name": "نام کالا",
        "brand": "برند",
        "model": "مدل",
        "quantity": "موجودی",
        "minimum": "حداقل",
        "status": "وضعیت"
    }

    for column, heading in headings.items():

        tree.heading(
            column,
            text=heading
        )

    widths = {
        "code": 120,
        "name": 220,
        "brand": 130,
        "model": 130,
        "quantity": 100,
        "minimum": 100,
        "status": 120
    }

    for column, width in widths.items():

        tree.column(
            column,
            width=width,
            anchor="center"
        )

    scrollbar = ttk.Scrollbar(
        table_frame,
        orient="vertical",
        command=tree.yview
    )

    tree.configure(
        yscrollcommand=scrollbar.set
    )

    tree.pack(
        side="left",
        fill="both",
        expand=True
    )

    scrollbar.pack(
        side="right",
        fill="y"
    )

    # ==================================================
    # LOAD LOW STOCK
    # ==================================================

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            product_code,
            name,
            brand,
            model,
            quantity,
            minimum_stock
        FROM products
        WHERE quantity <= minimum_stock
        ORDER BY quantity ASC
    """)

    low_products = cursor.fetchall()

    connection.close()

    if low_products:

        for product in low_products:

            quantity = product[4]

            if quantity == 0:
                status = "ناموجود"
            else:
                status = "موجودی کم"

            tree.insert(
                "",
                "end",
                values=(
                    product[0],
                    product[1],
                    product[2],
                    product[3],
                    product[4],
                    product[5],
                    status
                )
            )

    else:

        tree.insert(
            "",
            "end",
            values=(
                "-",
                "همه کالاها وضعیت مناسبی دارند",
                "-",
                "-",
                "-",
                "-",
                "✓ مناسب"
            )
        )

    # ==================================================
    # INITIAL PERFORMANCE
    # ==================================================

    dashboard_win.update_idletasks()

    load_performance()


def create_dashboard_card(
    parent,
    icon,
    title,
    value,
    bg_color,
    column
):

    card = tk.Frame(
        parent,
        bg=bg_color,
        width=250,
        height=105
    )

    card.grid(
        row=0,
        column=column,
        padx=7,
        pady=5,
        sticky="nsew"
    )

    card.grid_propagate(
        False
    )

    parent.grid_columnconfigure(
        column,
        weight=1
    )

    icon_label = tk.Label(
        card,
        text=icon,
        font=("Tahoma", 22),
        bg=bg_color
    )

    icon_label.pack(
        pady=(8, 0)
    )

    title_label = tk.Label(
        card,
        text=title,
        font=("Tahoma", 10),
        bg=bg_color,
        fg="#4B5563"
    )

    title_label.pack()

    value_label = tk.Label(
        card,
        text=value,
        font=("Tahoma", 14, "bold"),
        bg=bg_color,
        fg="#111827"
    )

    value_label.pack(
        pady=(2, 8)
    )


def format_price(price):

    return f"{price:,} تومان"

# ==================================================
# CATEGORY & BRAND MANAGEMENT
# ==================================================

def manage_categories_brands():
    if not require_permission("products", window): return

    manage_window = tk.Toplevel(window)

    manage_window.title(
        "مدیریت برند و دسته‌بندی"
    )

    manage_window.geometry(
        "1000x650"
    )

    manage_window.minsize(
        900,
        580
    )

    manage_window.configure(
        bg="#F4F6F8"
    )

    # ==================================================
    # HEADER
    # ==================================================

    header = tk.Frame(
        manage_window,
        bg="#FFFFFF"
    )

    header.pack(
        fill="x",
        padx=25,
        pady=(25, 15)
    )

    title = tk.Label(
        header,
        text="⚙️ مدیریت برند و دسته‌بندی",
        font=("Tahoma", 22, "bold"),
        bg="#FFFFFF",
        fg="#111827"
    )

    title.pack(
        pady=(18, 5)
    )

    subtitle = tk.Label(
        header,
        text="مدیریت اطلاعات پایه مورد استفاده در سیستم",
        font=("Tahoma", 11),
        bg="#FFFFFF",
        fg="#6B7280"
    )

    subtitle.pack(
        pady=(0, 18)
    )

    # ==================================================
    # MAIN CONTAINER
    # ==================================================

    main_frame = tk.Frame(
        manage_window,
        bg="#F4F6F8"
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=25,
        pady=5
    )

    main_frame.grid_columnconfigure(
        0,
        weight=1
    )

    main_frame.grid_columnconfigure(
        1,
        weight=1
    )

    main_frame.grid_rowconfigure(
        0,
        weight=1
    )

    # ==================================================
    # CATEGORY PANEL
    # ==================================================

    categories_panel = tk.Frame(
        main_frame,
        bg="#FFFFFF"
    )

    categories_panel.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=(0, 8)
    )

    category_header = tk.Frame(
        categories_panel,
        bg="#FFFFFF"
    )

    category_header.pack(
        fill="x",
        padx=20,
        pady=(20, 10)
    )

    category_icon = tk.Label(
        category_header,
        text="🏷️",
        font=("Tahoma", 24),
        bg="#FFFFFF"
    )

    category_icon.pack(
        side="right",
        padx=(0, 10)
    )

    category_title_frame = tk.Frame(
        category_header,
        bg="#FFFFFF"
    )

    category_title_frame.pack(
        side="right"
    )

    category_title = tk.Label(
        category_title_frame,
        text="دسته‌بندی‌ها",
        font=("Tahoma", 16, "bold"),
        bg="#FFFFFF",
        fg="#1F2937"
    )

    category_title.pack(
        anchor="e"
    )

    category_subtitle = tk.Label(
        category_title_frame,
        text="گروه‌بندی کالاهای فروشگاه",
        font=("Tahoma", 9),
        bg="#FFFFFF",
        fg="#9CA3AF"
    )

    category_subtitle.pack(
        anchor="e"
    )

    # --------------------------------------------------
    # CATEGORY LIST
    # --------------------------------------------------

    category_list_frame = tk.Frame(
        categories_panel,
        bg="#FFFFFF"
    )

    category_list_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=10
    )

    categories_list = tk.Listbox(
        category_list_frame,
        font=("Tahoma", 11),
        bg="#F9FAFB",
        fg="#374151",
        selectbackground="#DBEAFE",
        selectforeground="#1D4ED8",
        activestyle="none",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#E5E7EB",
        highlightcolor="#93C5FD"
    )

    category_scrollbar = tk.Scrollbar(
        category_list_frame,
        orient="vertical",
        command=categories_list.yview
    )

    categories_list.configure(
        yscrollcommand=category_scrollbar.set
    )

    categories_list.pack(
        side="left",
        fill="both",
        expand=True
    )

    category_scrollbar.pack(
        side="right",
        fill="y"
    )

    # --------------------------------------------------
    # CATEGORY INPUT
    # --------------------------------------------------

    category_input_frame = tk.Frame(
        categories_panel,
        bg="#FFFFFF"
    )

    category_input_frame.pack(
        fill="x",
        padx=20,
        pady=10
    )

    category_entry = tk.Entry(
        category_input_frame,
        font=("Tahoma", 11),
        justify="right",
        relief="flat",
        bd=0,
        bg="#F9FAFB",
        fg="#1F2937",
        highlightthickness=1,
        highlightbackground="#D1D5DB",
        highlightcolor="#60A5FA"
    )

    category_entry.pack(
        fill="x",
        ipady=9
    )

    # --------------------------------------------------
    # CATEGORY BUTTONS
    # --------------------------------------------------

    category_buttons = tk.Frame(
        categories_panel,
        bg="#FFFFFF"
    )

    category_buttons.pack(
        fill="x",
        padx=20,
        pady=(0, 20)
    )

    # ==================================================
    # CATEGORY FUNCTIONS
    # ==================================================

    def load_categories():

        categories_list.delete(
            0,
            tk.END
        )

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM categories
            ORDER BY name
        """)

        categories = cursor.fetchall()

        connection.close()

        for category in categories:

            categories_list.insert(
                tk.END,
                category[0]
            )

    def add_category():

        name = category_entry.get().strip()

        if not name:

            messagebox.showwarning(
                "اطلاعات ناقص",
                "نام دسته‌بندی را وارد کنید.",
                parent=manage_window
            )

            category_entry.focus()

            return

        connection = connect_database()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO categories (name)
                VALUES (?)
            """, (name,))

            connection.commit()

            category_entry.delete(
                0,
                tk.END
            )

            load_categories()

            messagebox.showinfo(
                "ثبت موفق",
                f"دسته‌بندی «{name}» با موفقیت اضافه شد.",
                parent=manage_window
            )

        except sqlite3.IntegrityError:

            messagebox.showerror(
                "خطا",
                "این دسته‌بندی قبلاً وجود دارد.",
                parent=manage_window
            )

        finally:

            connection.close()

    def delete_category():

        selected = categories_list.curselection()

        if not selected:

            messagebox.showwarning(
                "انتخاب دسته‌بندی",
                "ابتدا یک دسته‌بندی را انتخاب کنید.",
                parent=manage_window
            )

            return

        category_name = categories_list.get(
            selected[0]
        )

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE category = ?
        """, (category_name,))

        product_count = cursor.fetchone()[0]

        connection.close()

        if product_count > 0:

            messagebox.showwarning(
                "امکان حذف وجود ندارد",
                (
                    f"دسته‌بندی «{category_name}» "
                    f"در {product_count} کالا استفاده شده است.\n\n"
                    f"ابتدا دسته‌بندی کالاهای مربوطه را تغییر دهید."
                ),
                parent=manage_window
            )

            return

        answer = messagebox.askyesno(
            "تأیید حذف",
            f"آیا دسته‌بندی «{category_name}» حذف شود؟",
            parent=manage_window
        )

        if not answer:
            return

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM categories
            WHERE name = ?
        """, (category_name,))

        connection.commit()
        connection.close()

        load_categories()

    add_category_button = tk.Button(
        category_buttons,
        text="➕ افزودن دسته‌بندی",
        font=("Tahoma", 10, "bold"),
        bg="#2563EB",
        fg="#FFFFFF",
        activebackground="#1D4ED8",
        activeforeground="#FFFFFF",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=add_category
    )

    add_category_button.pack(
        side="right",
        fill="x",
        expand=True,
        padx=(5, 0),
        ipady=8
    )

    delete_category_button = tk.Button(
        category_buttons,
        text="🗑️ حذف",
        font=("Tahoma", 10, "bold"),
        bg="#FEF2F2",
        fg="#DC2626",
        activebackground="#FEE2E2",
        activeforeground="#B91C1C",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=delete_category
    )

    delete_category_button.pack(
        side="left",
        fill="x",
        expand=True,
        padx=(0, 5),
        ipady=8
    )

    # ==================================================
    # BRAND PANEL
    # ==================================================

    brands_panel = tk.Frame(
        main_frame,
        bg="#FFFFFF"
    )

    brands_panel.grid(
        row=0,
        column=1,
        sticky="nsew",
        padx=(8, 0)
    )

    brand_header = tk.Frame(
        brands_panel,
        bg="#FFFFFF"
    )

    brand_header.pack(
        fill="x",
        padx=20,
        pady=(20, 10)
    )

    brand_icon = tk.Label(
        brand_header,
        text="🏢",
        font=("Tahoma", 24),
        bg="#FFFFFF"
    )

    brand_icon.pack(
        side="right",
        padx=(0, 10)
    )

    brand_title_frame = tk.Frame(
        brand_header,
        bg="#FFFFFF"
    )

    brand_title_frame.pack(
        side="right"
    )

    brand_title = tk.Label(
        brand_title_frame,
        text="برندها",
        font=("Tahoma", 16, "bold"),
        bg="#FFFFFF",
        fg="#1F2937"
    )

    brand_title.pack(
        anchor="e"
    )

    brand_subtitle = tk.Label(
        brand_title_frame,
        text="مدیریت برندهای محصولات",
        font=("Tahoma", 9),
        bg="#FFFFFF",
        fg="#9CA3AF"
    )

    brand_subtitle.pack(
        anchor="e"
    )

    # --------------------------------------------------
    # BRAND LIST
    # --------------------------------------------------

    brand_list_frame = tk.Frame(
        brands_panel,
        bg="#FFFFFF"
    )

    brand_list_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=10
    )

    brands_list = tk.Listbox(
        brand_list_frame,
        font=("Tahoma", 11),
        bg="#F9FAFB",
        fg="#374151",
        selectbackground="#EDE9FE",
        selectforeground="#6D28D9",
        activestyle="none",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#E5E7EB",
        highlightcolor="#A78BFA"
    )

    brand_scrollbar = tk.Scrollbar(
        brand_list_frame,
        orient="vertical",
        command=brands_list.yview
    )

    brands_list.configure(
        yscrollcommand=brand_scrollbar.set
    )

    brands_list.pack(
        side="left",
        fill="both",
        expand=True
    )

    brand_scrollbar.pack(
        side="right",
        fill="y"
    )

    # --------------------------------------------------
    # BRAND INPUT
    # --------------------------------------------------

    brand_input_frame = tk.Frame(
        brands_panel,
        bg="#FFFFFF"
    )

    brand_input_frame.pack(
        fill="x",
        padx=20,
        pady=10
    )

    brand_entry = tk.Entry(
        brand_input_frame,
        font=("Tahoma", 11),
        justify="right",
        relief="flat",
        bd=0,
        bg="#F9FAFB",
        fg="#1F2937",
        highlightthickness=1,
        highlightbackground="#D1D5DB",
        highlightcolor="#A78BFA"
    )

    brand_entry.pack(
        fill="x",
        ipady=9
    )

    # --------------------------------------------------
    # BRAND BUTTONS
    # --------------------------------------------------

    brand_buttons = tk.Frame(
        brands_panel,
        bg="#FFFFFF"
    )

    brand_buttons.pack(
        fill="x",
        padx=20,
        pady=(0, 20)
    )

    # ==================================================
    # BRAND FUNCTIONS
    # ==================================================

    def load_brands():

        brands_list.delete(
            0,
            tk.END
        )

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM brands
            ORDER BY name
        """)

        brands = cursor.fetchall()

        connection.close()

        for brand in brands:

            brands_list.insert(
                tk.END,
                brand[0]
            )

    def add_brand():

        name = brand_entry.get().strip()

        if not name:

            messagebox.showwarning(
                "اطلاعات ناقص",
                "نام برند را وارد کنید.",
                parent=manage_window
            )

            brand_entry.focus()

            return

        connection = connect_database()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO brands (name)
                VALUES (?)
            """, (name,))

            connection.commit()

            brand_entry.delete(
                0,
                tk.END
            )

            load_brands()

            messagebox.showinfo(
                "ثبت موفق",
                f"برند «{name}» با موفقیت اضافه شد.",
                parent=manage_window
            )

        except sqlite3.IntegrityError:

            messagebox.showerror(
                "خطا",
                "این برند قبلاً وجود دارد.",
                parent=manage_window
            )

        finally:

            connection.close()

    def delete_brand():

        selected = brands_list.curselection()

        if not selected:

            messagebox.showwarning(
                "انتخاب برند",
                "ابتدا یک برند را انتخاب کنید.",
                parent=manage_window
            )

            return

        brand_name = brands_list.get(
            selected[0]
        )

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE brand = ?
        """, (brand_name,))

        product_count = cursor.fetchone()[0]

        connection.close()

        if product_count > 0:

            messagebox.showwarning(
                "امکان حذف وجود ندارد",
                (
                    f"برند «{brand_name}» "
                    f"در {product_count} کالا استفاده شده است.\n\n"
                    f"ابتدا برند کالاهای مربوطه را تغییر دهید."
                ),
                parent=manage_window
            )

            return

        answer = messagebox.askyesno(
            "تأیید حذف",
            f"آیا برند «{brand_name}» حذف شود؟",
            parent=manage_window
        )

        if not answer:
            return

        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM brands
            WHERE name = ?
        """, (brand_name,))

        connection.commit()
        connection.close()

        load_brands()

    add_brand_button = tk.Button(
        brand_buttons,
        text="➕ افزودن برند",
        font=("Tahoma", 10, "bold"),
        bg="#7C3AED",
        fg="#FFFFFF",
        activebackground="#6D28D9",
        activeforeground="#FFFFFF",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=add_brand
    )

    add_brand_button.pack(
        side="right",
        fill="x",
        expand=True,
        padx=(5, 0),
        ipady=8
    )

    delete_brand_button = tk.Button(
        brand_buttons,
        text="🗑️ حذف",
        font=("Tahoma", 10, "bold"),
        bg="#FEF2F2",
        fg="#DC2626",
        activebackground="#FEE2E2",
        activeforeground="#B91C1C",
        relief="flat",
        bd=0,
        cursor="hand2",
        command=delete_brand
    )

    delete_brand_button.pack(
        side="left",
        fill="x",
        expand=True,
        padx=(0, 5),
        ipady=8
    )

    # ==================================================
    # KEYBOARD SHORTCUTS
    # ==================================================

    category_entry.bind(
        "<Return>",
        lambda event: add_category()
    )

    brand_entry.bind(
        "<Return>",
        lambda event: add_brand()
    )

    # ==================================================
    # INITIAL LOAD
    # ==================================================

    load_categories()
    load_brands()

# ==================================================
# FINAL BUSINESS UTILITIES
# ==================================================

def get_setting(key, default=""):
    try:
        con=connect_database(); cur=con.cursor(); cur.execute("SELECT value FROM app_settings WHERE key=?",(key,)); row=cur.fetchone(); con.close()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def set_setting(key, value):
    con=connect_database(); cur=con.cursor(); cur.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value))); con.commit(); con.close()


def refresh_installment_statuses():
    """همگام‌سازی وضعیت اقساط با تاریخ روز، بدون تغییر مبلغ پرداخت‌شده."""
    con=connect_database(); cur=con.cursor()
    cur.execute("SELECT id,due_date,amount,paid_amount FROM installments")
    rows=cur.fetchall()
    for iid,due,amount,paid in rows:
        st=due_status(due,paid or 0,amount or 0)
        cur.execute("UPDATE installments SET status=? WHERE id=?",(st,iid))
    con.commit(); con.close()


def open_overdue_installments(parent=None):
    if not require_permission("reports", parent or window): return
    refresh_installment_statuses()
    w=tk.Toplevel(parent or window); w.title("اقساط سررسید گذشته"); w.geometry("1050x600"); w.configure(bg="#F4F6F8")
    tk.Label(w,text="⚠️ اقساط سررسید گذشته",font=("Tahoma",20,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    frame=tk.Frame(w,bg="white"); frame.pack(fill="both",expand=True,padx=20,pady=20)
    cols=("id","customer","sale","num","due","amount","paid","remain","status")
    tree=ttk.Treeview(frame,columns=cols,show="headings")
    heads={"id":"شناسه","customer":"مشتری","sale":"فروش","num":"قسط","due":"سررسید","amount":"مبلغ","paid":"پرداخت","remain":"مانده","status":"وضعیت"}
    for c in cols: tree.heading(c,text=heads[c]); tree.column(c,width=105,anchor="center")
    tree.column("customer",width=180,anchor="e"); tree.pack(fill="both",expand=True,padx=10,pady=10)
    con=connect_database(); cur=con.cursor(); cur.execute("""SELECT i.id,c.name,i.sale_id,i.installment_number,i.due_date,i.amount,i.paid_amount,i.status FROM installments i JOIN sales s ON s.id=i.sale_id LEFT JOIN customers c ON c.id=s.customer_id WHERE i.amount>i.paid_amount AND date(i.due_date)<date('now') ORDER BY i.due_date"""); rows=cur.fetchall(); con.close()
    for r in rows: tree.insert("","end",iid=str(r[0]),values=(r[0],r[1] or '-',r[2],r[3],display_due_date(r[4]),f"{r[5]:,}",f"{r[6]:,}",f"{max(0,r[5]-r[6]):,}","سررسید گذشته"))
    def pay():
        sel=tree.selection()
        if sel: record_installment_payment(int(sel[0]),w)
    tk.Button(w,text="💳 ثبت پرداخت قسط انتخاب‌شده",command=pay,bg="#16A34A",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold"),cursor="hand2").pack(pady=(0,20),ipadx=20,ipady=7)


def reports_window():
    if not require_permission("reports", window): return
    refresh_installment_statuses()
    w=tk.Toplevel(window); w.title("گزارش‌های مالی"); w.geometry("1000x650"); w.configure(bg="#F4F6F8")
    tk.Label(w,text="📊 گزارش‌های مالی",font=("Tahoma",20,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    con=connect_database(); cur=con.cursor()
    cur.execute("SELECT COALESCE(SUM(total_amount),0),COALESCE(SUM(paid_amount),0),COALESCE(SUM(remaining_amount),0),COUNT(*) FROM sales")
    total_sales,received,debt,sale_count=cur.fetchone()
    cur.execute("SELECT COUNT(*),COALESCE(SUM(amount-paid_amount),0) FROM installments WHERE amount>paid_amount AND date(due_date)<date('now')")
    overdue_count,overdue_debt=cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(buy_price*quantity),0),COALESCE(SUM(sell_price*quantity),0) FROM products")
    stock_buy,stock_sell=cur.fetchone()
    con.close()
    cards=[("تعداد فروش",sale_count),("مجموع فروش",f"{total_sales:,} تومان"),("دریافتی",f"{received:,} تومان"),("بدهی مشتریان",f"{debt:,} تومان"),("اقساط عقب‌افتاده",overdue_count),("مبلغ عقب‌افتاده",f"{overdue_debt:,} تومان"),("ارزش خرید موجودی",f"{stock_buy:,} تومان"),("ارزش فروش موجودی",f"{stock_sell:,} تومان")]
    grid=tk.Frame(w,bg="#F4F6F8"); grid.pack(fill="both",expand=True,padx=25,pady=25)
    for i,(title,val) in enumerate(cards):
        r,c=divmod(i,2); card=tk.Frame(grid,bg="white",highlightbackground="#E5E7EB",highlightthickness=1); card.grid(row=r,column=c,padx=10,pady=10,sticky="nsew"); grid.columnconfigure(c,weight=1); grid.rowconfigure(r,weight=1)
        tk.Label(card,text=title,font=("Tahoma",10,"bold"),bg="white",fg="#64748B").pack(pady=(25,8)); tk.Label(card,text=str(val),font=("Tahoma",17,"bold"),bg="white",fg="#111827").pack(pady=(0,25))
    tk.Button(w,text="⚠️ مشاهده اقساط سررسید گذشته",command=lambda: open_overdue_installments(w),bg="#F59E0B",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(pady=(0,20),ipadx=20,ipady=7)


def change_password_window(parent=None):
    if not CURRENT_USER: return
    w=tk.Toplevel(parent or window); w.title("تغییر رمز عبور"); w.geometry("430x390"); w.configure(bg="#F4F6F8")
    tk.Label(w,text="🔑 تغییر رمز عبور",font=("Tahoma",18,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    form=tk.Frame(w,bg="white"); form.pack(fill="both",expand=True,padx=25,pady=25)
    vals=[tk.StringVar(),tk.StringVar(),tk.StringVar()]
    for lab,var in zip(("رمز فعلی","رمز جدید","تکرار رمز جدید"),vals):
        tk.Label(form,text=lab,font=("Tahoma",10,"bold"),bg="white").pack(anchor="e",padx=20,pady=(15,4)); tk.Entry(form,textvariable=var,show="•",justify="right",font=("Tahoma",11)).pack(fill="x",padx=20,ipady=7)
    def save():
        old,new,again=[v.get() for v in vals]
        if not old or not new: messagebox.showerror("خطا","همه فیلدها الزامی است.",parent=w); return
        if hash_password(old) != get_user_password_hash(CURRENT_USER["id"]): messagebox.showerror("خطا","رمز فعلی صحیح نیست.",parent=w); return
        if len(new)<4: messagebox.showerror("خطا","رمز جدید حداقل ۴ کاراکتر باشد.",parent=w); return
        if new!=again: messagebox.showerror("خطا","تکرار رمز جدید یکسان نیست.",parent=w); return
        con=connect_database(); cur=con.cursor(); cur.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(new),CURRENT_USER["id"])); con.commit(); con.close(); log_action("تغییر رمز عبور","user",CURRENT_USER["id"]); messagebox.showinfo("موفق","رمز عبور تغییر کرد.",parent=w); w.destroy()
    tk.Button(form,text="ذخیره رمز جدید",command=save,bg="#4F46E5",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(fill="x",padx=20,pady=25,ipady=8)


def get_user_password_hash(user_id):
    con=connect_database(); cur=con.cursor(); cur.execute("SELECT password_hash FROM users WHERE id=?",(user_id,)); row=cur.fetchone(); con.close(); return row[0] if row else ""


def settings_window():
    if not require_permission("settings", window): return
    w=tk.Toplevel(window); w.title("تنظیمات فروشگاه"); w.geometry("550x500"); w.configure(bg="#F4F6F8")
    tk.Label(w,text="⚙️ تنظیمات فروشگاه",font=("Tahoma",20,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    form=tk.Frame(w,bg="white"); form.pack(fill="both",expand=True,padx=25,pady=25)
    fields=[("نام فروشگاه","store_name"),("تلفن فروشگاه","store_phone"),("آدرس","store_address"),("پیشوند فاکتور","invoice_prefix")]
    vars=[]
    for lab,key in fields:
        v=tk.StringVar(value=get_setting(key)); vars.append((key,v)); tk.Label(form,text=lab,font=("Tahoma",10,"bold"),bg="white").pack(anchor="e",padx=20,pady=(15,4)); tk.Entry(form,textvariable=v,justify="right",font=("Tahoma",10)).pack(fill="x",padx=20,ipady=7)
    def save():
        for k,v in vars: set_setting(k,v.get().strip())
        log_action("تغییر تنظیمات فروشگاه"); messagebox.showinfo("موفق","تنظیمات ذخیره شد.",parent=w); w.destroy()
    tk.Button(form,text="💾 ذخیره تنظیمات",command=save,bg="#16A34A",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(fill="x",padx=20,pady=25,ipady=8)

# ==================================================
# AUTHENTICATION / USER MANAGEMENT
# ==================================================

def backup_database():
    if not require_permission("all", window): return
    if not os.path.exists(DATABASE):
        messagebox.showerror("پشتیبان‌گیری", "فایل پایگاه داده پیدا نشد.", parent=window); return
    os.makedirs("backups", exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=os.path.abspath(os.path.join("backups", f"inventory_backup_{stamp}.db"))
    shutil.copy2(DATABASE,path)
    log_action("پشتیبان‌گیری از پایگاه داده", "database", None, path)
    messagebox.showinfo("پشتیبان‌گیری موفق", f"نسخه پشتیبان ساخته شد.\n{path}", parent=window)


def login_window(root):
    global CURRENT_USER
    result = {"ok": False}
    login = tk.Toplevel(root)
    login.title("ورود به سیستم")
    login.geometry("430x360")
    login.resizable(False, False)
    login.configure(bg="#F4F6F8")
    login.transient(root)
    login.grab_set()
    tk.Label(login, text="🔐 ورود به سیستم", font=("Tahoma", 20, "bold"), bg="#111827", fg="white", height=2).pack(fill="x")
    form=tk.Frame(login,bg="white",highlightbackground="#E5E7EB",highlightthickness=1); form.pack(fill="both",expand=True,padx=25,pady=25)
    user=tk.StringVar(); pw=tk.StringVar()
    tk.Label(form,text="نام کاربری",font=("Tahoma",10,"bold"),bg="white").pack(anchor="e",padx=25,pady=(25,5))
    ue=tk.Entry(form,textvariable=user,justify="right",font=("Tahoma",11)); ue.pack(fill="x",padx=25,ipady=7)
    tk.Label(form,text="رمز عبور",font=("Tahoma",10,"bold"),bg="white").pack(anchor="e",padx=25,pady=(15,5))
    pe=tk.Entry(form,textvariable=pw,show="•",justify="right",font=("Tahoma",11)); pe.pack(fill="x",padx=25,ipady=7)
    def do_login(event=None):
        global CURRENT_USER
        try:
            username = user.get().strip()
            password = pw.get()
            if not username or not password:
                messagebox.showwarning("ورود", "نام کاربری و رمز عبور را وارد کنید.", parent=login)
                return
            con=connect_database(); cur=con.cursor()
            cur.execute("SELECT id,username,full_name,role FROM users WHERE username=? AND password_hash=? AND active=1", (username, hash_password(password)))
            row=cur.fetchone(); con.close()
            if not row:
                messagebox.showerror("ورود ناموفق", "نام کاربری یا رمز عبور صحیح نیست.", parent=login)
                return
            CURRENT_USER={"id":row[0],"username":row[1],"full_name":row[2],"role":row[3]}
            result["ok"]=True
            login.grab_release()
            login.destroy()
            root.deiconify()
            root.lift()
            root.focus_force()
        except Exception as exc:
            import traceback
            try:
                with open(os.path.join(BASE_DIR, "startup_error.log"), "a", encoding="utf-8") as f:
                    f.write("\n--- LOGIN ERROR ---\n")
                    traceback.print_exc(file=f)
            except Exception:
                pass
            messagebox.showerror("خطای ورود", f"ورود انجام نشد و برنامه بسته نمی‌شود.\n\n{exc}\n\nجزئیات در startup_error.log ذخیره شد.", parent=login)
    tk.Button(form,text="ورود",command=do_login,bg="#4F46E5",fg="white",relief="flat",bd=0,font=("Tahoma",11,"bold"),cursor="hand2").pack(fill="x",padx=25,pady=(20,8),ipady=8)
    def reset_default_admin():
        if user.get().strip() != "admin":
            messagebox.showwarning("بازیابی مدیر", "برای بازیابی، نام کاربری را admin وارد کنید.", parent=login); return
        if not messagebox.askyesno("بازیابی مدیر", "رمز مدیر به admin123 برگردانده شود؟", parent=login): return
        con=connect_database(); cur=con.cursor()
        cur.execute("SELECT id FROM users WHERE username='admin'")
        row=cur.fetchone()
        if row:
            cur.execute("UPDATE users SET password_hash=?,active=1,role='admin' WHERE id=?", (hash_password("admin123"), row[0]))
        else:
            cur.execute("INSERT INTO users(username,password_hash,full_name,role,active,created_at) VALUES(?,?,?,?,?,?)", ("admin",hash_password("admin123"),"مدیر سیستم","admin",1,now_storage_datetime()))
        con.commit(); con.close()
        messagebox.showinfo("انجام شد", "رمز مدیر به admin123 تنظیم شد. اکنون وارد شوید.", parent=login)
    tk.Button(form,text="🔑 بازیابی ورود مدیر",command=reset_default_admin,bg="#E5E7EB",fg="#111827",relief="flat",bd=0,font=("Tahoma",9,"bold"),cursor="hand2").pack(fill="x",padx=25,pady=(0,10),ipady=6)
    tk.Label(form,text="ورود اولیه: admin / admin123  |  در صورت مشکل از بازیابی مدیر استفاده کنید.",font=("Tahoma",8),bg="white",fg="#64748B").pack()
    login.bind("<Return>",do_login); ue.focus()
    root.wait_window(login)
    return result["ok"]


def user_management_window():
    if not require_permission("all"): return
    win=tk.Toplevel(window); win.title("مدیریت کاربران و سطوح دسترسی"); win.geometry("900x620"); win.configure(bg="#F4F6F8")
    tk.Label(win,text="👥 مدیریت کاربران",font=("Tahoma",20,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    main=tk.Frame(win,bg="#F4F6F8"); main.pack(fill="both",expand=True,padx=20,pady=20)
    tree=ttk.Treeview(main,columns=("id","username","name","role","active"),show="headings")
    for c,h in [("id","شناسه"),("username","نام کاربری"),("name","نام"),("role","سطح دسترسی"),("active","فعال")]: tree.heading(c,text=h); tree.column(c,width=150,anchor="center")
    tree.pack(fill="both",expand=True)
    def load():
        for i in tree.get_children(): tree.delete(i)
        con=connect_database(); cur=con.cursor(); cur.execute("SELECT id,username,full_name,role,active FROM users ORDER BY id"); rows=cur.fetchall(); con.close()
        for r in rows: tree.insert("","end",iid=str(r[0]),values=(r[0],r[1],r[2],ROLE_NAMES.get(r[3],r[3]),"بله" if r[4] else "خیر"))
    def add_user():
        d=tk.Toplevel(win); d.title("کاربر جدید"); d.geometry("430x430"); d.configure(bg="#F4F6F8")
        vars=[tk.StringVar() for _ in range(4)]
        labels=["نام کاربری","نام و نام خانوادگی","رمز عبور","سطح دسترسی"]
        for idx,(lab,var) in enumerate(zip(labels,vars)):
            tk.Label(d,text=lab,font=("Tahoma",10,"bold"),bg="#F4F6F8").pack(anchor="e",padx=25,pady=(15,4))
            if idx==3: ttk.Combobox(d,textvariable=var,values=list(ROLE_NAMES.keys()),state="readonly",justify="right").pack(fill="x",padx=25,ipady=5)
            else: tk.Entry(d,textvariable=var,show="•" if idx==2 else "",justify="right").pack(fill="x",padx=25,ipady=7)
        def save():
            if not all(v.get().strip() for v in vars): messagebox.showerror("خطا","همه فیلدها الزامی است.",parent=d); return
            if vars[3].get() not in ROLE_NAMES: messagebox.showerror("خطا","سطح دسترسی را انتخاب کنید.",parent=d); return
            try:
                con=connect_database(); cur=con.cursor(); cur.execute("INSERT INTO users(username,password_hash,full_name,role,active,created_at) VALUES(?,?,?,?,?,?)",(vars[0].get().strip(),hash_password(vars[2].get()),vars[1].get().strip(),vars[3].get(),1,now_storage_datetime())); con.commit(); con.close(); log_action("ایجاد کاربر","user",None,vars[0].get()); d.destroy(); load()
            except sqlite3.IntegrityError: messagebox.showerror("خطا","این نام کاربری قبلاً وجود دارد.",parent=d)
        tk.Button(d,text="ذخیره",command=save,bg="#16A34A",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(fill="x",padx=25,pady=25,ipady=8)
    def edit_user():
        sel=tree.selection()
        if not sel: messagebox.showwarning("انتخاب کاربر","یک کاربر را انتخاب کنید.",parent=win); return
        uid=int(sel[0])
        con=connect_database(); cur=con.cursor(); cur.execute("SELECT username,full_name,role FROM users WHERE id=?",(uid,)); row=cur.fetchone(); con.close()
        if not row: return
        d=tk.Toplevel(win); d.title("ویرایش کاربر"); d.geometry("430x360"); d.configure(bg="#F4F6F8")
        u,n,r=[tk.StringVar(value=x or "") for x in row]; newpw=tk.StringVar()
        for lab,var in (("نام کاربری",u),("نام و نام خانوادگی",n),("سطح دسترسی",r),("رمز جدید (اختیاری)",newpw)):
            tk.Label(d,text=lab,font=("Tahoma",10,"bold"),bg="#F4F6F8").pack(anchor="e",padx=25,pady=(14,4))
            if var is r: ttk.Combobox(d,textvariable=var,values=list(ROLE_NAMES.keys()),state="readonly",justify="right").pack(fill="x",padx=25,ipady=5)
            else: tk.Entry(d,textvariable=var,show="•" if var is newpw else "",justify="right").pack(fill="x",padx=25,ipady=7)
        def save_edit():
            if not u.get().strip() or not n.get().strip() or r.get() not in ROLE_NAMES: messagebox.showerror("خطا","اطلاعات کاربر معتبر نیست.",parent=d); return
            if uid==CURRENT_USER["id"] and r.get()!="admin" and CURRENT_USER["role"]=="admin":
                pass
            con=connect_database(); cur=con.cursor()
            try:
                if newpw.get():
                    if len(newpw.get())<4: raise ValueError("رمز جدید حداقل ۴ کاراکتر باشد.")
                    cur.execute("UPDATE users SET username=?,full_name=?,role=?,password_hash=? WHERE id=?",(u.get().strip(),n.get().strip(),r.get(),hash_password(newpw.get()),uid))
                else:
                    cur.execute("UPDATE users SET username=?,full_name=?,role=? WHERE id=?",(u.get().strip(),n.get().strip(),r.get(),uid))
                con.commit(); con.close(); log_action("ویرایش کاربر","user",uid); d.destroy(); load()
            except sqlite3.IntegrityError: con.close(); messagebox.showerror("خطا","نام کاربری تکراری است.",parent=d)
            except ValueError as e: con.close(); messagebox.showerror("خطا",str(e),parent=d)
        tk.Button(d,text="💾 ذخیره تغییرات",command=save_edit,bg="#4F46E5",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(fill="x",padx=25,pady=20,ipady=8)

    def toggle():
        sel=tree.selection()
        if not sel: return
        uid=int(sel[0])
        if CURRENT_USER and uid==CURRENT_USER["id"]: messagebox.showwarning("هشدار","کاربر فعلی را نمی‌توان غیرفعال کرد.",parent=win); return
        con=connect_database(); cur=con.cursor(); cur.execute("UPDATE users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(uid,)); con.commit(); con.close(); load()
    tk.Button(win,text="➕ کاربر جدید",command=add_user,bg="#4F46E5",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(side="right",padx=25,pady=15,ipadx=20,ipady=7)
    tk.Button(win,text="✏️ ویرایش کاربر",command=edit_user,bg="#6366F1",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(side="right",pady=15,ipadx=20,ipady=7)
    tk.Button(win,text="فعال/غیرفعال",command=toggle,bg="#F59E0B",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold")).pack(side="right",pady=15,ipadx=20,ipady=7)
    load()


# ==================================================
# MAIN WINDOW - MODERN DESIGN
# ==================================================

# ==================================================
# SAFE STARTUP
# ==================================================

def show_startup_error(title, exc):
    try:
        log_path = os.path.join(BASE_DIR, "startup_error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "="*70 + "\n")
            f.write(datetime.now().isoformat() + "\n")
            import traceback
            traceback.print_exc(file=f)
        messagebox.showerror(title, f"برنامه هنگام اجرا با خطا مواجه شد.\n\n{exc}\n\nگزارش خطا در startup_error.log ذخیره شد.")
    except Exception:
        pass

try:
    create_database()
    refresh_installment_statuses()
except Exception as exc:
    import traceback
    try:
        with open(os.path.join(BASE_DIR, "startup_error.log"), "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass
    raise

window = tk.Tk()

def global_exception_handler(exc_type, exc_value, exc_traceback):
    import traceback
    try:
        with open(os.path.join(BASE_DIR, "startup_error.log"), "a", encoding="utf-8") as f:
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        messagebox.showerror("خطای برنامه", f"یک خطای غیرمنتظره رخ داد:\n\n{exc_value}\n\nجزئیات در startup_error.log ذخیره شد.", parent=window)
    except Exception:
        pass

import sys
sys.excepthook = global_exception_handler

window.title(
    "سیستم مدیریت موجودی فروشگاه"
)

window.geometry(
    "1200x750"
)

window.minsize(
    1050,
    700
)

window.configure(
    bg="#F5F7FA"
)

if not login_window(window):
    window.destroy()
    raise SystemExit


# ==================================================
# COLORS
# ==================================================

BG_COLOR = "#F5F7FA"
WHITE = "#FFFFFF"

TEXT_DARK = "#1F2937"
TEXT_GRAY = "#6B7280"

PRIMARY = "#4F46E5"
PRIMARY_HOVER = "#4338CA"

GREEN = "#10B981"
GREEN_HOVER = "#059669"

BLUE = "#3B82F6"
BLUE_HOVER = "#2563EB"

PURPLE = "#8B5CF6"
PURPLE_HOVER = "#7C3AED"

ORANGE = "#F59E0B"
ORANGE_HOVER = "#D97706"

RED = "#EF4444"
RED_HOVER = "#DC2626"

BORDER = "#E5E7EB"


# ==================================================
# WINDOW HEADER
# ==================================================

header = tk.Frame(
    window,
    bg=WHITE,
    height=90
)

header.pack(
    fill="x"
)

header.pack_propagate(False)


# -----------------------------
# Header Right
# -----------------------------

header_right = tk.Frame(
    header,
    bg=WHITE
)

header_right.pack(
    side="right",
    padx=35
)


app_icon = tk.Label(
    header_right,
    text="📦",
    font=("Tahoma", 30),
    bg=WHITE,
    fg=PRIMARY
)

app_icon.pack(
    side="right",
    padx=(15, 0)
)


header_text_frame = tk.Frame(
    header_right,
    bg=WHITE
)

header_text_frame.pack(
    side="right"
)


app_title = tk.Label(
    header_text_frame,
    text="سیستم مدیریت موجودی",
    font=("Tahoma", 18, "bold"),
    bg=WHITE,
    fg=TEXT_DARK
)

app_title.pack(
    anchor="e"
)


app_subtitle = tk.Label(
    header_text_frame,
    text="مدیریت هوشمند کالا و انبار فروشگاه",
    font=("Tahoma", 9),
    bg=WHITE,
    fg=TEXT_GRAY
)

app_subtitle.pack(
    anchor="e"
)


# -----------------------------
# Header Left
# -----------------------------

header_left = tk.Frame(
    header,
    bg=WHITE
)

header_left.pack(
    side="left",
    padx=35
)


status_dot = tk.Label(
    header_left,
    text="●",
    font=("Tahoma", 12),
    bg=WHITE,
    fg=GREEN
)

status_dot.pack(
    side="left",
    padx=(0, 6)
)


status_label = tk.Label(
    header_left,
    text=f"کاربر: {CURRENT_USER.get('full_name','-')} | {ROLE_NAMES.get(CURRENT_USER.get('role',''), CURRENT_USER.get('role',''))}",
    font=("Tahoma", 10, "bold"),
    bg=WHITE,
    fg=TEXT_GRAY
)

status_label.pack(
    side="left"
)


# ==================================================
# MAIN CONTENT
# ==================================================

content = tk.Frame(
    window,
    bg=BG_COLOR
)

content.pack(
    fill="both",
    expand=True,
    padx=45,
    pady=35
)


# ==================================================
# WELCOME SECTION
# ==================================================

welcome_frame = tk.Frame(
    content,
    bg=BG_COLOR
)

welcome_frame.pack(
    fill="x",
    pady=(0, 25)
)


welcome_text = tk.Label(
    welcome_frame,
    text="مدیریت فروشگاه",
    font=("Tahoma", 26, "bold"),
    bg=BG_COLOR,
    fg=TEXT_DARK
)

welcome_text.pack(
    anchor="e"
)


welcome_description = tk.Label(
    welcome_frame,
    text="همه ابزارهای موردنیاز برای مدیریت موجودی در یک محیط ساده و حرفه‌ای",
    font=("Tahoma", 11),
    bg=BG_COLOR,
    fg=TEXT_GRAY
)

welcome_description.pack(
    anchor="e",
    pady=(5, 0)
)


# ==================================================
# QUICK ACTIONS TITLE
# ==================================================

actions_title = tk.Label(
    content,
    text="دسترسی سریع",
    font=("Tahoma", 15, "bold"),
    bg=BG_COLOR,
    fg=TEXT_DARK
)

actions_title.pack(
    anchor="e",
    pady=(0, 12)
)


def logout_and_relogin():
    global CURRENT_USER
    if not messagebox.askyesno("خروج از حساب", "از حساب کاربری فعلی خارج شوید؟", parent=window): return
    log_action("خروج از سیستم")
    CURRENT_USER=None
    if not login_window(window):
        window.destroy(); raise SystemExit
    messagebox.showinfo("ورود مجدد", "ورود مجدد انجام شد. برای اعمال سطح دسترسی جدید، پنجره اصلی تازه‌سازی شد.", parent=window)


# ==================================================
# BUTTON AREA
# ==================================================

buttons_frame = tk.Frame(
    content,
    bg=BG_COLOR
)

buttons_frame.pack(
    fill="x"
)


# ==================================================
# MODERN BUTTON FUNCTION
# ==================================================

def create_modern_button(
    parent,
    text,
    icon,
    bg,
    hover_bg,
    command,
    row,
    column
):

    button_frame = tk.Frame(
        parent,
        bg=WHITE,
        highlightbackground=BORDER,
        highlightthickness=1
    )

    button_frame.grid(
        row=row,
        column=column,
        padx=8,
        pady=8,
        sticky="nsew"
    )

    button_frame.grid_propagate(False)

    button_frame.configure(
        width=250,
        height=105
    )


    button = tk.Button(
        button_frame,
        text=f"{icon}\n{text}",
        font=("Tahoma", 12, "bold"),
        bg=bg,
        fg=TEXT_DARK,
        activebackground=hover_bg,
        activeforeground=WHITE,
        relief="flat",
        bd=0,
        cursor="hand2",
        command=command
    )

    button.pack(
        fill="both",
        expand=True,
        padx=5,
        pady=5
    )


    def on_enter(event):

        button.configure(
            bg=hover_bg,
            fg=WHITE
        )


    def on_leave(event):

        button.configure(
            bg=bg,
            fg=TEXT_DARK
        )


    button.bind(
        "<Enter>",
        on_enter
    )

    button.bind(
        "<Leave>",
        on_leave
    )


# ==================================================
# GRID CONFIGURATION
# ==================================================

for column in range(4):

    buttons_frame.columnconfigure(
        column,
        weight=1
    )


# ==================================================
# SALES
# ==================================================

def sales_window():
    if not require_permission("sales", window): return

    sale_window = tk.Toplevel(window)
    sale_window.title("🛒 ثبت فروش")
    sale_window.geometry("1250x900")
    sale_window.minsize(1050, 760)
    sale_window.configure(bg="#F4F6F8")

    header = tk.Frame(sale_window, bg="#4F46E5", height=105)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(header, text="🛒", font=("Tahoma", 30), bg="#4F46E5", fg="white").pack(
        side="right", padx=(20, 35), pady=20
    )
    header_text = tk.Frame(header, bg="#4F46E5")
    header_text.pack(side="right", pady=18)
    tk.Label(header_text, text="ثبت فروش", font=("Tahoma", 20, "bold"),
             bg="#4F46E5", fg="white").pack(anchor="e")
    tk.Label(header_text, text="فروش نقدی یا اقساطی با برنامه اقساط قابل ویرایش",
             font=("Tahoma", 10), bg="#4F46E5", fg="#E0E7FF").pack(anchor="e", pady=(4, 0))

    outer_frame = tk.Frame(sale_window, bg="#F4F6F8")
    outer_frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer_frame, bg="#F4F6F8", highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    main_frame = tk.Frame(canvas, bg="#F4F6F8")
    canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")

    def update_scroll_region(event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
    main_frame.bind("<Configure>", update_scroll_region)

    def resize_canvas(event):
        canvas.itemconfigure(canvas_window, width=event.width)
    canvas.bind("<Configure>", resize_canvas)

    def mouse_wheel(event):
        if event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", mouse_wheel)

    def close_sale_window():
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        sale_window.destroy()
    sale_window.protocol("WM_DELETE_WINDOW", close_sale_window)

    # ---------------- CUSTOMER ----------------
    customer_card = tk.Frame(main_frame, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    customer_card.pack(fill="x", padx=30, pady=(25, 15))
    customer_var = tk.StringVar()
    tk.Label(customer_card, text="👤 مشتری", font=("Tahoma", 11, "bold"), bg="white", fg="#374151").pack(
        side="right", padx=(25, 10), pady=18
    )
    customer_combo = ttk.Combobox(customer_card, textvariable=customer_var, state="readonly",
                                  font=("Tahoma", 10), justify="right", width=45)
    customer_combo.pack(side="right", padx=10, pady=14, ipady=7)

    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute("SELECT id, name, phone FROM customers ORDER BY name")
    customers = cursor.fetchall()
    connection.close()
    customer_dictionary = {}
    customer_values = []
    for customer_id, customer_name, customer_phone in customers:
        display = f"{customer_name} | {customer_phone}" if customer_phone else customer_name
        customer_values.append(display)
        customer_dictionary[display] = customer_id
    customer_combo["values"] = customer_values

    # ---------------- PRODUCT ----------------
    product_card = tk.Frame(main_frame, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    product_card.pack(fill="x", padx=30, pady=(0, 15))
    product_card.columnconfigure(1, weight=1)
    product_var = tk.StringVar()
    quantity_var = tk.StringVar(value="1")
    current_stock_var = tk.StringVar(value="موجودی: -")
    cash_price_var = tk.StringVar(value="قیمت نقدی: -")

    tk.Label(product_card, text="📦 کالا", font=("Tahoma", 11, "bold"), bg="white", fg="#374151").grid(
        row=0, column=4, padx=15, pady=18
    )
    products = get_products_for_combobox()
    product_dictionary = {}
    product_values = []
    for product in products:
        display = f"{product[1]} | {product[2]} | {product[3]} | {product[4]} | موجودی: {product[5]:,}"
        product_values.append(display)
        product_dictionary[display] = product
    product_combo = ttk.Combobox(product_card, textvariable=product_var, values=product_values,
                                 state="readonly", font=("Tahoma", 10), justify="right")
    product_combo.grid(row=0, column=1, padx=10, pady=14, sticky="ew", ipady=7)

    tk.Label(product_card, textvariable=current_stock_var, font=("Tahoma", 9, "bold"),
             bg="#F9FAFB", fg="#475569", padx=10, pady=7).grid(row=0, column=2, padx=5, pady=14)
    tk.Label(product_card, textvariable=cash_price_var, font=("Tahoma", 9, "bold"),
             bg="#ECFDF5", fg="#047857", padx=10, pady=7).grid(row=0, column=3, padx=5, pady=14)

    def update_product_info(event=None):
        selected = product_combo.get().strip()
        product = product_dictionary.get(selected)
        if not product:
            current_stock_var.set("موجودی: -")
            cash_price_var.set("قیمت نقدی: -")
            return
        current_stock_var.set(f"موجودی: {product[5]:,} عدد")
        cash_price_var.set(f"قیمت نقدی: {product[6]:,} تومان")
    product_combo.bind("<<ComboboxSelected>>", update_product_info)

    tk.Label(product_card, text="تعداد", font=("Tahoma", 10, "bold"), bg="white", fg="#374151").grid(
        row=0, column=0, padx=(15, 5), pady=18
    )
    quantity_entry = tk.Entry(product_card, textvariable=quantity_var, font=("Tahoma", 11), justify="center",
                              width=8, relief="flat", bg="#F9FAFB", highlightthickness=1,
                              highlightbackground="#D1D5DB")
    quantity_entry.grid(row=0, column=0, padx=(65, 10), pady=14, ipady=7)

    # ---------------- CART ----------------
    cart_card = tk.Frame(main_frame, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    cart_card.pack(fill="both", padx=30, pady=(0, 15))
    cart_title = tk.Frame(cart_card, bg="white")
    cart_title.pack(fill="x", padx=15, pady=12)
    tk.Label(cart_title, text="📋 سبد فروش", font=("Tahoma", 13, "bold"), bg="white", fg="#111827").pack(side="right")
    cart_count_var = tk.StringVar(value="0 کالا")
    tk.Label(cart_title, textvariable=cart_count_var, font=("Tahoma", 9, "bold"), bg="#EEF2FF", fg="#4F46E5",
             padx=10, pady=5).pack(side="left")
    cart_frame = tk.Frame(cart_card, bg="white", height=220)
    cart_frame.pack(fill="both", expand=True, padx=15)
    cart_frame.pack_propagate(False)
    cart_tree = ttk.Treeview(cart_frame, columns=("code", "name", "quantity", "unit_price", "total"),
                             show="headings", selectmode="browse")
    for col, heading, width, anchor in [
        ("code", "کد کالا", 120, "center"), ("name", "نام کالا", 350, "e"),
        ("quantity", "تعداد", 100, "center"), ("unit_price", "قیمت نقدی واحد", 180, "center"),
        ("total", "مبلغ نقدی", 180, "center")]:
        cart_tree.heading(col, text=heading)
        cart_tree.column(col, width=width, anchor=anchor)
    cart_scroll = ttk.Scrollbar(cart_frame, orient="vertical", command=cart_tree.yview)
    cart_tree.configure(yscrollcommand=cart_scroll.set)
    cart_scroll.pack(side="right", fill="y")
    cart_tree.pack(side="left", fill="both", expand=True)
    cart = []

    def refresh_cart():
        for item in cart_tree.get_children():
            cart_tree.delete(item)
        for index, item in enumerate(cart):
            total_price = item["quantity"] * item["unit_price"]
            cart_tree.insert("", "end", iid=str(index), values=(
                item["product_code"], item["name"], f"{item['quantity']:,}",
                f"{item['unit_price']:,}", f"{total_price:,}"
            ))
        cart_count_var.set(f"{len(cart):,} کالا")
        update_totals()

    def add_to_cart():
        selected = product_combo.get().strip()
        if not selected:
            messagebox.showwarning("انتخاب کالا", "لطفاً ابتدا یک کالا انتخاب کنید.", parent=sale_window)
            return
        try:
            quantity = int(quantity_var.get().strip())
        except ValueError:
            messagebox.showerror("خطا", "تعداد باید عدد صحیح باشد.", parent=sale_window)
            return
        if quantity <= 0:
            messagebox.showerror("خطا", "تعداد باید بیشتر از صفر باشد.", parent=sale_window)
            return
        product = product_dictionary.get(selected)
        if not product:
            messagebox.showerror("خطا", "کالای انتخاب‌شده پیدا نشد.", parent=sale_window)
            return
        product_id, product_code, product_name, product_category, product_brand, current_quantity, unit_price = product[:7]
        if current_quantity <= 0:
            messagebox.showerror("کالا ناموجود است", f"کالای «{product_name}» موجود نیست.", parent=sale_window)
            return
        existing = next((x for x in cart if x["product_id"] == product_id), None)
        existing_quantity = existing["quantity"] if existing else 0
        if existing_quantity + quantity > current_quantity:
            messagebox.showerror("موجودی کافی نیست", f"موجودی «{product_name}»: {current_quantity:,} عدد", parent=sale_window)
            return
        if existing:
            existing["quantity"] += quantity
            existing["total_price"] = existing["quantity"] * unit_price
        else:
            cart.append({"product_id": product_id, "product_code": product_code, "name": product_name,
                         "quantity": quantity, "unit_price": unit_price, "total_price": quantity * unit_price})
        quantity_var.set("1")
        refresh_cart()
        product_combo.focus()

    tk.Button(product_card, text="➕ افزودن به سبد", font=("Tahoma", 10, "bold"), bg="#4F46E5", fg="white",
              activebackground="#4338CA", relief="flat", bd=0, cursor="hand2", command=add_to_cart).grid(
        row=0, column=5, padx=15, pady=14, ipady=7
    )

    def remove_cart_item():
        selected = cart_tree.selection()
        if not selected:
            messagebox.showwarning("انتخاب کالا", "یک کالا را از سبد انتخاب کنید.", parent=sale_window)
            return
        cart.pop(int(selected[0]))
        refresh_cart()
    tk.Button(cart_card, text="🗑️ حذف از سبد", font=("Tahoma", 10, "bold"), bg="#FEF2F2", fg="#DC2626",
              relief="flat", bd=0, cursor="hand2", command=remove_cart_item).pack(anchor="e", padx=15, pady=12)

    # ---------------- PAYMENT ----------------
    payment_card = tk.Frame(main_frame, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    payment_card.pack(fill="x", padx=30, pady=(0, 15))
    for c in range(5):
        payment_card.columnconfigure(c, weight=1)

    cash_total_var = tk.StringVar(value="0 تومان")
    installment_total_var = tk.StringVar(value="0")
    down_payment_var = tk.StringVar(value="0")
    remaining_var = tk.StringVar(value="0 تومان")
    payment_type_var = tk.StringVar(value="نقدی")
    installment_count_var = tk.StringVar(value="3")
    installment_interval_var = tk.StringVar(value="30")
    installment_info_var = tk.StringVar(value="")

    def cash_total():
        return sum(x["quantity"] * x["unit_price"] for x in cart)

    def parse_nonnegative(var, title):
        try:
            value = int(var.get().strip() or 0)
        except ValueError:
            raise ValueError(f"{title} باید عدد صحیح باشد.")
        if value < 0:
            raise ValueError(f"{title} نمی‌تواند منفی باشد.")
        return value

    def update_totals(*args):
        cash = cash_total()
        cash_total_var.set(f"{cash:,} تومان")
        if not installment_total_var.get().strip() or installment_total_var.get() == "0":
            installment_total_var.set(str(cash))
        try:
            final_total = parse_nonnegative(installment_total_var, "مبلغ نهایی فروش")
            down = parse_nonnegative(down_payment_var, "پیش‌پرداخت")
        except ValueError:
            remaining_var.set("-")
            installment_info_var.set("اطلاعات مبلغ را اصلاح کنید.")
            return
        if down > final_total:
            remaining_var.set("-")
        else:
            remaining_var.set(f"{final_total - down:,} تومان")
        update_installment_info()

    labels = [
        ("قیمت نقدی کالاها", cash_total_var, 4),
        ("مبلغ نهایی فروش", installment_total_var, 3),
        ("پیش‌پرداخت", down_payment_var, 2),
        ("باقی‌مانده اقساط", remaining_var, 1),
        ("نوع پرداخت", payment_type_var, 0),
    ]
    for title, var, col in labels:
        tk.Label(payment_card, text=title, font=("Tahoma", 10, "bold"), bg="white", fg="#374151").grid(
            row=0, column=col, padx=10, pady=(15, 5)
        )
        if col == 4 or col == 1:
            tk.Label(payment_card, textvariable=var, font=("Tahoma", 12 if col == 1 else 14, "bold"),
                     bg="white", fg="#4F46E5" if col == 4 else "#DC2626").grid(row=1, column=col, padx=10, pady=(0, 15))
        elif col == 0:
            ttk.Combobox(payment_card, textvariable=var, values=["نقدی", "کارت", "نسیه", "اقساط"],
                         state="readonly", width=14, font=("Tahoma", 10), justify="center").grid(
                row=1, column=col, padx=10, pady=(0, 15), ipady=5
            )
        else:
            tk.Entry(payment_card, textvariable=var, width=18, font=("Tahoma", 10), justify="center",
                     relief="flat", bg="#F9FAFB", highlightthickness=1, highlightbackground="#D1D5DB").grid(
                row=1, column=col, padx=10, pady=(0, 15), ipady=6
            )

    # ---------------- INSTALLMENT EDITABLE TABLE ----------------
    installment_frame = tk.Frame(main_frame, bg="white", highlightbackground="#C7D2FE", highlightthickness=1)
    installment_title = tk.Frame(installment_frame, bg="#EEF2FF")
    installment_title.pack(fill="x")
    tk.Label(installment_title, text="📅 برنامه اقساط — مبلغ و تاریخ هر قسط قابل ویرایش است",
             font=("Tahoma", 12, "bold"), bg="#EEF2FF", fg="#3730A3").pack(anchor="e", padx=20, pady=12)

    installment_controls = tk.Frame(installment_frame, bg="white")
    installment_controls.pack(fill="x", padx=20, pady=12)
    tk.Label(installment_controls, text="تعداد اقساط:", font=("Tahoma", 10, "bold"), bg="white").pack(side="right", padx=(15, 5))
    installment_count_entry = tk.Entry(installment_controls, textvariable=installment_count_var, width=7,
                                       font=("Tahoma", 10), justify="center", relief="flat", bg="#F9FAFB")
    installment_count_entry.pack(side="right", padx=5, ipady=6)
    tk.Label(installment_controls, text="فاصله (روز):", font=("Tahoma", 10, "bold"), bg="white").pack(side="right", padx=(25, 5))
    installment_interval_entry = tk.Entry(installment_controls, textvariable=installment_interval_var, width=7,
                                          font=("Tahoma", 10), justify="center", relief="flat", bg="#F9FAFB")
    installment_interval_entry.pack(side="right", padx=5, ipady=6)
    tk.Label(installment_controls, textvariable=installment_info_var, font=("Tahoma", 9, "bold"),
             bg="#F8FAFC", fg="#4F46E5", padx=15, pady=8).pack(side="right", padx=20)

    installment_table_frame = tk.Frame(installment_frame, bg="white", height=230)
    installment_table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))
    installment_table_frame.pack_propagate(False)
    installment_tree = ttk.Treeview(installment_table_frame,
        columns=("number", "amount", "due_date"), show="headings", selectmode="browse")
    installment_tree.heading("number", text="قسط")
    installment_tree.heading("amount", text="مبلغ قسط")
    installment_tree.heading("due_date", text="تاریخ سررسید")
    installment_tree.column("number", width=90, anchor="center")
    installment_tree.column("amount", width=220, anchor="center")
    installment_tree.column("due_date", width=180, anchor="center")
    inst_scroll = ttk.Scrollbar(installment_table_frame, orient="vertical", command=installment_tree.yview)
    installment_tree.configure(yscrollcommand=inst_scroll.set)
    inst_scroll.pack(side="right", fill="y")
    installment_tree.pack(side="left", fill="both", expand=True)
    installment_rows = []

    def installment_remaining():
        final_total = parse_nonnegative(installment_total_var, "مبلغ نهایی فروش")
        down = parse_nonnegative(down_payment_var, "پیش‌پرداخت")
        if down > final_total:
            raise ValueError("پیش‌پرداخت نمی‌تواند بیشتر از مبلغ نهایی فروش باشد.")
        return final_total - down

    def validate_date(value):
        try:
            jalali_date_to_gregorian(value)
            return True
        except Exception:
            return False

    def rebuild_installment_table():
        if payment_type_var.get() != "اقساط":
            return
        try:
            count = int(installment_count_var.get().strip())
            interval = int(installment_interval_var.get().strip())
            remaining = installment_remaining()
            if count <= 0 or interval <= 0:
                raise ValueError
        except ValueError:
            installment_info_var.set("تعداد، فاصله و مبلغ اقساط را اصلاح کنید.")
            return
        old = {row["number"]: row for row in installment_rows}
        installment_rows.clear()
        for item in installment_tree.get_children():
            installment_tree.delete(item)
        base, rem = divmod(remaining, count)
        for i in range(1, count + 1):
            amount = base + (1 if i <= rem else 0)
            due = jalali_date_to_gregorian(add_days_to_jalali(jalali_today(), interval * i))
            if i in old:
                amount = old[i]["amount"]
                due = old[i]["due_date"]
            row = {"number": i, "amount": amount, "due_date": due}
            installment_rows.append(row)
            installment_tree.insert("", "end", iid=str(i), values=(i, f"{amount:,}", display_due_date(due)))
        update_installment_info()

    def update_installment_info(*args):
        if payment_type_var.get() != "اقساط":
            installment_info_var.set("")
            return
        try:
            remaining = installment_remaining()
            count = int(installment_count_var.get().strip())
            if count <= 0:
                raise ValueError
            installment_info_var.set(f"باقی‌مانده: {remaining:,} تومان | جمع اقساط باید دقیقاً برابر باشد")
        except ValueError as e:
            installment_info_var.set(str(e))

    def edit_installment():
        selected = installment_tree.selection()
        if not selected:
            messagebox.showwarning("انتخاب قسط", "یک قسط را انتخاب کنید.", parent=sale_window)
            return
        number = int(selected[0])
        row = next(x for x in installment_rows if x["number"] == number)
        edit = tk.Toplevel(sale_window)
        edit.title(f"ویرایش قسط {number}")
        edit.geometry("420x260")
        edit.resizable(False, False)
        edit.configure(bg="#F4F6F8")
        amount_var = tk.StringVar(value=str(row["amount"]))
        date_var = tk.StringVar(value=display_due_date(row["due_date"]))
        tk.Label(edit, text=f"ویرایش قسط شماره {number}", font=("Tahoma", 14, "bold"), bg="#F4F6F8").pack(pady=18)
        form = tk.Frame(edit, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
        form.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        tk.Label(form, text="مبلغ قسط:", font=("Tahoma", 10, "bold"), bg="white").grid(row=0, column=1, padx=15, pady=15)
        tk.Entry(form, textvariable=amount_var, width=22, justify="center", font=("Tahoma", 11)).grid(row=0, column=0, padx=15, pady=15)
        tk.Label(form, text="تاریخ سررسید شمسی (YYYY-MM-DD):", font=("Tahoma", 10, "bold"), bg="white").grid(row=1, column=1, padx=15, pady=15)
        tk.Entry(form, textvariable=date_var, width=22, justify="center", font=("Tahoma", 11)).grid(row=1, column=0, padx=15, pady=15)
        def save_edit():
            try:
                amount = int(amount_var.get().strip())
                if amount <= 0:
                    raise ValueError("مبلغ قسط باید بیشتر از صفر باشد.")
            except ValueError as e:
                messagebox.showerror("خطا", str(e), parent=edit)
                return
            due_j = date_var.get().strip()
            if not validate_date(due_j):
                messagebox.showerror("خطای تاریخ", "تاریخ شمسی باید با فرمت YYYY-MM-DD باشد.", parent=edit)
                return
            row["amount"] = amount
            row["due_date"] = jalali_date_to_gregorian(due_j)
            installment_tree.item(str(number), values=(number, f"{amount:,}", display_due_date(row["due_date"])))
            edit.destroy()
            update_installment_info()
        tk.Button(form, text="💾 ذخیره تغییر", command=save_edit, bg="#4F46E5", fg="white",
                  relief="flat", bd=0, font=("Tahoma", 10, "bold"), cursor="hand2").grid(
            row=2, column=0, columnspan=2, padx=15, pady=15, ipady=7, sticky="ew"
        )

    tk.Button(installment_frame, text="✏️ ویرایش قسط انتخاب‌شده", command=edit_installment,
              bg="#EEF2FF", fg="#3730A3", relief="flat", bd=0, font=("Tahoma", 10, "bold"), cursor="hand2").pack(
        anchor="e", padx=20, pady=(0, 15), ipadx=12, ipady=6
    )

    def update_visibility(*args):
        if payment_type_var.get() == "اقساط":
            installment_frame.pack(fill="x", padx=30, pady=(0, 15))
            rebuild_installment_table()
        else:
            installment_frame.pack_forget()
            installment_rows.clear()
            for item in installment_tree.get_children():
                installment_tree.delete(item)
    payment_type_combo = None
    payment_type_var.trace_add("write", update_visibility)
    installment_count_var.trace_add("write", rebuild_installment_table)
    installment_interval_var.trace_add("write", rebuild_installment_table)
    installment_total_var.trace_add("write", update_totals)
    down_payment_var.trace_add("write", update_totals)

    # locate payment combobox created above and bind a variable-safe refresh
    # ---------------- SAVE ----------------
    def save_sale():
        if not cart:
            messagebox.showerror("سبد فروش خالی است", "حداقل یک کالا به سبد فروش اضافه کنید.", parent=sale_window)
            return
        customer_text = customer_combo.get().strip()
        customer_id = customer_dictionary.get(customer_text)
        if customer_id is None:
            messagebox.showerror("مشتری", "لطفاً یک مشتری معتبر انتخاب کنید.", parent=sale_window)
            return
        cash = cash_total()
        try:
            if payment_type_var.get() == "اقساط":
                final_total = parse_nonnegative(installment_total_var, "مبلغ نهایی فروش")
                down = parse_nonnegative(down_payment_var, "پیش‌پرداخت")
                count = int(installment_count_var.get().strip())
                interval = int(installment_interval_var.get().strip())
                if final_total <= 0:
                    raise ValueError("مبلغ نهایی فروش باید بیشتر از صفر باشد.")
                if down > final_total:
                    raise ValueError("پیش‌پرداخت نمی‌تواند بیشتر از مبلغ نهایی فروش باشد.")
                if count <= 0 or interval <= 0:
                    raise ValueError("تعداد اقساط و فاصله سررسید باید بیشتر از صفر باشند.")
                remaining = final_total - down
                if remaining <= 0:
                    raise ValueError("برای فروش اقساطی باید مبلغی باقی‌مانده باشد.")
                if len(installment_rows) != count:
                    rebuild_installment_table()
                installment_sum = sum(x["amount"] for x in installment_rows)
                if installment_sum != remaining:
                    messagebox.showerror(
                        "عدم تطابق اقساط",
                        f"جمع اقساط: {installment_sum:,} تومان\n"
                        f"باقی‌مانده: {remaining:,} تومان\n\n"
                        "جمع اقساط + پیش‌پرداخت باید دقیقاً برابر مبلغ فروش قسطی باشد.",
                        parent=sale_window
                    )
                    return
                for row in installment_rows:
                    if row["amount"] <= 0 or not validate_date(row["due_date"]):
                        messagebox.showerror("اطلاعات قسط", "مبلغ و تاریخ تمام اقساط را صحیح وارد کنید.", parent=sale_window)
                        return
            else:
                final_total = cash
                down = final_total
                count = 0
                interval = 0
                remaining = 0
                installment_sum = 0
        except ValueError as error:
            messagebox.showerror("خطای اطلاعات", str(error), parent=sale_window)
            return

        payment_type = payment_type_var.get()
        confirmation = (
            f"مبلغ نقدی کالاها: {cash:,} تومان\n"
            f"مبلغ نهایی فروش: {final_total:,} تومان\n"
            f"پیش‌پرداخت: {down:,} تومان\n"
            f"باقی‌مانده: {remaining:,} تومان\n"
            f"نوع پرداخت: {payment_type}"
        )
        if payment_type == "اقساط":
            confirmation += f"\nتعداد اقساط: {count}\nفاصله سررسید: هر {interval} روز\nجمع اقساط: {installment_sum:,} تومان"
        if not messagebox.askyesno("تأیید فروش", confirmation, parent=sale_window):
            return

        connection = connect_database()
        cursor = connection.cursor()
        try:
            sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO sales (
                    customer_id, sale_date, payment_type, total_amount, paid_amount,
                    remaining_amount, notes, cash_total, down_payment, installment_count,
                    installment_interval
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (customer_id, sale_date, payment_type, final_total, down, remaining, "",
                  cash, down, count, interval))
            sale_id = cursor.lastrowid

            for item in cart:
                cursor.execute("SELECT quantity FROM products WHERE id = ?", (item["product_id"],))
                stock = cursor.fetchone()
                if not stock:
                    raise Exception(f"کالای «{item['name']}» پیدا نشد.")
                if item["quantity"] > stock[0]:
                    raise Exception(f"موجودی «{item['name']}» کافی نیست. موجودی فعلی: {stock[0]:,}")
                item_total = item["quantity"] * item["unit_price"]
                cursor.execute("""
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (sale_id, item["product_id"], item["quantity"], item["unit_price"], item_total))
                cursor.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?",
                               (item["quantity"], item["product_id"]))
                cursor.execute("""
                    INSERT INTO stock_movements (product_id, movement_type, quantity, date)
                    VALUES (?, ?, ?, ?)
                """, (item["product_id"], "فروش", item["quantity"], sale_date))

            if payment_type == "اقساط":
                for row in installment_rows:
                    cursor.execute("""
                        INSERT INTO installments (
                            sale_id, installment_number, due_date, amount, paid_amount,
                            payment_date, status, notes, cash_total, installment_total,
                            down_payment, interval_days, installment_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sale_id, row["number"], row["due_date"], row["amount"], 0, None,
                          "پرداخت نشده", "", cash, final_total, down, interval, count))

            connection.commit()
            messagebox.showinfo("فروش موفق", f"فروش شماره {sale_id} با موفقیت ثبت شد.\n\n"
                                f"مبلغ فروش: {final_total:,} تومان\n"
                                f"پیش‌پرداخت: {down:,} تومان\n"
                                f"باقی‌مانده: {remaining:,} تومان", parent=sale_window)
            close_sale_window()
        except Exception as error:
            connection.rollback()
            messagebox.showerror("خطا در ثبت فروش", f"ثبت فروش انجام نشد.\n\n{error}", parent=sale_window)
        finally:
            connection.close()

    tk.Button(main_frame, text="💾 ثبت نهایی فروش", font=("Tahoma", 13, "bold"), bg="#16A34A", fg="white",
              activebackground="#15803D", relief="flat", bd=0, cursor="hand2", command=save_sale).pack(
        fill="x", padx=30, pady=(0, 30), ipady=11
    )
    quantity_entry.bind("<Return>", lambda event: add_to_cart())
    installment_count_entry.bind("<FocusOut>", rebuild_installment_table)
    installment_interval_entry.bind("<FocusOut>", rebuild_installment_table)
    sale_window.bind("<Escape>", lambda event: close_sale_window())

    update_totals()
    update_visibility()
    customer_combo.focus()


def mark_installment_unpaid(installment_id, parent=None):
    if not require_permission("payments", parent): return
    con=connect_database(); cur=con.cursor(); cur.execute("SELECT due_date,amount,paid_amount,installment_number FROM installments WHERE id=?",(installment_id,)); row=cur.fetchone()
    if not row: con.close(); return
    due,amount,paid,num=row
    if paid and paid >= amount:
        con.close(); messagebox.showinfo("وضعیت قسط","این قسط قبلاً به‌طور کامل پرداخت شده است.",parent=parent); return
    if not messagebox.askyesno("ثبت عدم پرداخت",f"قسط شماره {num} به مبلغ {amount:,} تومان هنوز پرداخت نشده است.\n\nوضعیت آن به‌عنوان «پرداخت نشده/سررسید گذشته» ثبت شود؟",parent=parent):
        con.close(); return
    st=due_status(due,paid or 0,amount or 0)
    cur.execute("UPDATE installments SET status=? WHERE id=?",(st,installment_id)); con.commit(); con.close(); log_action("ثبت عدم پرداخت قسط","installment",installment_id,st)
    messagebox.showinfo("ثبت شد",f"وضعیت قسط شماره {num} ثبت شد: {st}",parent=parent)


# ==================================================
# SALES HISTORY / CUSTOMER FILE
# ==================================================

def ensure_invoice(sale_id):
    con=connect_database(); cur=con.cursor()
    cur.execute("SELECT invoice_number FROM invoices WHERE sale_id=?",(sale_id,)); row=cur.fetchone()
    if row: con.close(); return row[0]
    number=f"{get_setting('invoice_prefix','INV')}-{datetime.now().year}-{sale_id:06d}"
    cur.execute("INSERT INTO invoices(sale_id,invoice_number,created_at) VALUES(?,?,?)",(sale_id,number,now_storage_datetime()))
    con.commit(); con.close(); return number


def generate_invoice(sale_id, parent=None):
    if not require_permission("invoice", parent): return
    con=connect_database(); cur=con.cursor()
    cur.execute("""SELECT s.id,s.sale_date,s.payment_type,s.total_amount,s.paid_amount,s.remaining_amount,
                          COALESCE(s.cash_total,s.total_amount),COALESCE(s.down_payment,s.paid_amount),
                          c.name,c.phone,c.national_id,c.address FROM sales s LEFT JOIN customers c ON c.id=s.customer_id WHERE s.id=?""",(sale_id,)); sale=cur.fetchone()
    if not sale: con.close(); return
    cur.execute("""SELECT p.product_code,p.name,si.quantity,si.unit_price,si.total_price FROM sale_items si JOIN products p ON p.id=si.product_id WHERE si.sale_id=? ORDER BY si.id""",(sale_id,)); items=cur.fetchall()
    cur.execute("SELECT installment_number,due_date,amount,paid_amount,status FROM installments WHERE sale_id=? ORDER BY installment_number",(sale_id,)); inst=cur.fetchall(); con.close()
    invoice_no=ensure_invoice(sale_id)
    os.makedirs("invoices",exist_ok=True); path=os.path.abspath(os.path.join("invoices",invoice_no+".html"))
    rows="".join(f"<tr><td>{i[0]}</td><td>{i[1]}</td><td>{i[2]:,}</td><td>{i[3]:,}</td><td>{i[4]:,}</td></tr>" for i in items)
    inst_rows="".join(f"<tr><td>{i[0]}</td><td>{display_due_date(i[1])}</td><td>{i[2]:,}</td><td>{i[3]:,}</td><td>{i[4]}</td></tr>" for i in inst)
    html=f"""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>{invoice_no}</title><style>body{{font-family:Tahoma,Arial;max-width:900px;margin:30px auto;color:#111}}h1{{text-align:center}}.box{{border:1px solid #ddd;padding:15px;margin:15px 0}}table{{width:100%;border-collapse:collapse;margin:12px 0}}th,td{{border:1px solid #ccc;padding:8px;text-align:center}}th{{background:#f1f5f9}}.totals{{font-weight:bold}}</style><h1>فاکتور فروش</h1><div style="text-align:center"><b>{get_setting('store_name','فروشگاه')}</b><br>{get_setting('store_phone','')}<br>{get_setting('store_address','')}</div><div class="box"><b>شماره فاکتور:</b> {invoice_no}<br><b>تاریخ:</b> {display_sale_date(sale[1])}<br><b>مشتری:</b> {sale[8] or '-'} | <b>تلفن:</b> {sale[9] or '-'}</div><table><tr><th>کد</th><th>کالا</th><th>تعداد</th><th>قیمت واحد</th><th>جمع</th></tr>{rows}</table><div class="box totals">قیمت نقدی کالاها: {sale[6]:,} تومان<br>مبلغ نهایی فروش: {sale[3]:,} تومان<br>پیش‌پرداخت: {sale[7]:,} تومان<br>پرداخت‌شده: {sale[4]:,} تومان<br>باقی‌مانده: {sale[5]:,} تومان<br>نوع پرداخت: {sale[2]}</div>{('<h2>برنامه اقساط</h2><table><tr><th>قسط</th><th>سررسید</th><th>مبلغ</th><th>پرداخت شده</th><th>وضعیت</th></tr>'+inst_rows+'</table>') if inst else ''}<script>window.onload=function(){{window.print()}}</script></html>"""
    with open(path,"w",encoding="utf-8") as f: f.write(html)
    log_action("صدور فاکتور","sale",sale_id,invoice_no); webbrowser.open("file://"+path)


def record_installment_payment(installment_id, parent=None):
    if not require_permission("payments", parent): return
    con=connect_database(); cur=con.cursor(); cur.execute("""SELECT i.id,i.sale_id,i.installment_number,i.amount,i.paid_amount,i.due_date,i.status,c.name FROM installments i JOIN sales s ON s.id=i.sale_id LEFT JOIN customers c ON c.id=s.customer_id WHERE i.id=?""",(installment_id,)); row=cur.fetchone(); con.close()
    if not row: return
    iid,sale_id,num,amount,paid,due,status,cname=row; remaining=max(0,amount-paid)
    d=tk.Toplevel(parent or window); d.title(f"ثبت پرداخت قسط {num}"); d.geometry("430x360"); d.configure(bg="#F4F6F8")
    tk.Label(d,text=f"💳 پرداخت قسط شماره {num}",font=("Tahoma",16,"bold"),bg="#111827",fg="white",height=2).pack(fill="x")
    tk.Label(d,text=f"مشتری: {cname or '-'}\nمبلغ قسط: {amount:,} تومان\nپرداخت قبلی: {paid:,} تومان\nباقی‌مانده قسط: {remaining:,} تومان\nسررسید: {display_due_date(due)}",justify="right",anchor="e",font=("Tahoma",10,"bold"),bg="white",padx=20,pady=15).pack(fill="x",padx=20,pady=20)
    pv=tk.StringVar(value=str(remaining)); nv=tk.StringVar()
    tk.Label(d,text="مبلغ پرداختی",font=("Tahoma",10,"bold"),bg="#F4F6F8").pack(anchor="e",padx=25); tk.Entry(d,textvariable=pv,justify="center",font=("Tahoma",11)).pack(fill="x",padx=25,ipady=7)
    tk.Label(d,text="یادداشت",font=("Tahoma",10,"bold"),bg="#F4F6F8").pack(anchor="e",padx=25,pady=(10,3)); tk.Entry(d,textvariable=nv,justify="right",font=("Tahoma",10)).pack(fill="x",padx=25,ipady=7)
    def save():
        try: pay=int(pv.get().strip() or 0)
        except ValueError: messagebox.showerror("خطا","مبلغ پرداختی باید عدد باشد.",parent=d); return
        if pay<=0 or pay>remaining: messagebox.showerror("خطا",f"مبلغ باید بین 1 تا {remaining:,} تومان باشد.",parent=d); return
        con=connect_database(); cur=con.cursor(); new_paid=paid+pay; pay_date=now_storage_datetime(); new_status=due_status(due,new_paid,amount)
        cur.execute("UPDATE installments SET paid_amount=?,payment_date=?,status=?,notes=? WHERE id=?",(new_paid,pay_date,new_status,nv.get().strip(),iid))
        cur.execute("INSERT INTO installment_payments(installment_id,amount,payment_date,payment_method,reference,notes,recorded_by) VALUES(?,?,?,?,?,?,?)",(iid,pay,pay_date,'نقدی','',nv.get().strip(),(CURRENT_USER or {}).get('id')))
        cur.execute("SELECT COALESCE(down_payment,paid_amount,0), total_amount FROM sales WHERE id=?",(sale_id,)); sale_totals=cur.fetchone(); down=sale_totals[0] or 0; total_amount=sale_totals[1] or 0
        cur.execute("SELECT COALESCE(SUM(paid_amount),0) FROM installments WHERE sale_id=?",(sale_id,)); inst_paid=cur.fetchone()[0] or 0
        total_paid=down+inst_paid
        cur.execute("UPDATE sales SET paid_amount=?,remaining_amount=? WHERE id=?",(total_paid,max(0,total_amount-total_paid),sale_id))
        con.commit(); con.close(); log_action("ثبت پرداخت قسط","installment",iid,f"{pay}"); d.destroy()
        try: parent.destroy(); sale_detail_window(sale_id,parent and parent.master if hasattr(parent,'master') else window)
        except Exception: pass
    tk.Button(d,text="✓ ثبت پرداخت",command=save,bg="#16A34A",fg="white",relief="flat",bd=0,font=("Tahoma",11,"bold")).pack(fill="x",padx=25,pady=20,ipady=8)


def sale_detail_window(sale_id, parent=None):

    detail = tk.Toplevel(parent or window)
    detail.title(f"جزئیات فروش شماره {sale_id}")
    detail.geometry("1050x700")
    detail.minsize(900, 600)
    detail.configure(bg="#F4F6F8")

    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT s.id, s.sale_date, s.payment_type, s.total_amount, s.paid_amount,
               s.remaining_amount, s.cash_total, s.down_payment, s.installment_count,
               s.installment_interval, c.name, c.phone
        FROM sales s
        LEFT JOIN customers c ON c.id = s.customer_id
        WHERE s.id = ?
    """, (sale_id,))
    sale = cursor.fetchone()
    if not sale:
        connection.close()
        messagebox.showerror("خطا", "فروش پیدا نشد.", parent=detail)
        detail.destroy()
        return

    cursor.execute("""
        SELECT si.quantity, si.unit_price, si.total_price,
               p.product_code, p.name
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id = ?
        ORDER BY si.id
    """, (sale_id,))
    items = cursor.fetchall()

    cursor.execute("""
        SELECT installment_number, due_date, amount, paid_amount, status
        FROM installments
        WHERE sale_id = ?
        ORDER BY installment_number
    """, (sale_id,))
    installments = cursor.fetchall()
    connection.close()

    header = tk.Frame(detail, bg="#111827", height=90)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text=f"📄 جزئیات فروش شماره {sale_id}", font=("Tahoma", 18, "bold"),
             bg="#111827", fg="white").pack(anchor="e", padx=25, pady=22)

    summary = tk.Frame(detail, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    summary.pack(fill="x", padx=25, pady=20)
    info = (
        f"مشتری: {sale[10] or '-'} | تماس: {sale[11] or '-'}    "
        f"تاریخ شمسی: {display_sale_date(sale[1])}    نوع: {sale[2]}\n"
        f"قیمت نقدی: {sale[6]:,} تومان    مبلغ نهایی فروش: {sale[3]:,} تومان    "
        f"پیش‌پرداخت: {sale[7]:,} تومان    باقی‌مانده: {sale[5]:,} تومان"
    )
    if sale[8]:
        info += f"\nتعداد اقساط: {sale[8]}    فاصله سررسید: هر {sale[9]} روز"
    tk.Label(summary, text=info, justify="right", anchor="e", font=("Tahoma", 10, "bold"),
             bg="white", fg="#374151", padx=20, pady=15).pack(fill="x")

    items_frame = tk.Frame(detail, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    items_frame.pack(fill="both", expand=True, padx=25, pady=(0, 15))
    tk.Label(items_frame, text="اقلام فروش", font=("Tahoma", 12, "bold"), bg="white", fg="#111827").pack(anchor="e", padx=15, pady=10)
    item_tree = ttk.Treeview(items_frame, columns=("code", "name", "qty", "price", "total"), show="headings", height=6)
    for col, heading in [("code", "کد"), ("name", "کالا"), ("qty", "تعداد"), ("price", "قیمت نقدی واحد"), ("total", "جمع")]:
        item_tree.heading(col, text=heading)
        item_tree.column(col, width=160 if col != "name" else 300, anchor="center")
    for row in items:
        item_tree.insert("", "end", values=(row[3], row[4], row[0], f"{row[1]:,}", f"{row[2]:,}"))
    item_tree.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    if installments:
        inst_frame = tk.Frame(detail, bg="white", highlightbackground="#C7D2FE", highlightthickness=1)
        inst_frame.pack(fill="both", expand=True, padx=25, pady=(0, 20))
        tk.Label(inst_frame, text="برنامه اقساط", font=("Tahoma", 12, "bold"), bg="white", fg="#3730A3").pack(anchor="e", padx=15, pady=10)
        inst_tree = ttk.Treeview(inst_frame, columns=("num", "date", "amount", "paid", "status"), show="headings", height=6)
        for col, heading in [("num", "قسط"), ("date", "سررسید"), ("amount", "مبلغ"), ("paid", "پرداخت شده"), ("status", "وضعیت")]:
            inst_tree.heading(col, text=heading)
            inst_tree.column(col, width=150, anchor="center")
        for row in installments:
            inst_tree.insert("", "end", values=(row[0], display_due_date(row[1]), f"{row[2]:,}", f"{row[3]:,}", due_status(row[1],row[3],row[2])))
        inst_tree.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    action_bar = tk.Frame(detail, bg="#F4F6F8")
    action_bar.pack(fill="x", padx=25, pady=(0, 15))
    tk.Button(action_bar, text="🧾 صدور فاکتور", command=lambda: generate_invoice(sale_id, detail), bg="#4F46E5", fg="white", relief="flat", bd=0, font=("Tahoma",10,"bold"), cursor="hand2").pack(side="right", padx=5, ipadx=18, ipady=7)
    if installments:
        def pay_selected():
            sel=inst_tree.selection()
            if not sel: messagebox.showwarning("انتخاب قسط","یک قسط را انتخاب کنید.",parent=detail); return
            # find by displayed row number
            num=int(inst_tree.item(sel[0],"values")[0])
            con=connect_database(); cur=con.cursor(); cur.execute("SELECT id FROM installments WHERE sale_id=? AND installment_number=?",(sale_id,num)); rr=cur.fetchone(); con.close()
            if rr: record_installment_payment(rr[0], detail)
        tk.Button(action_bar, text="💳 ثبت پرداخت قسط", command=pay_selected, bg="#16A34A", fg="white", relief="flat", bd=0, font=("Tahoma",10,"bold"), cursor="hand2").pack(side="right", padx=5, ipadx=18, ipady=7)
        def mark_unpaid_selected():
            sel=inst_tree.selection()
            if not sel: messagebox.showwarning("انتخاب قسط","یک قسط را انتخاب کنید.",parent=detail); return
            num=int(inst_tree.item(sel[0],"values")[0])
            con=connect_database(); cur=con.cursor(); cur.execute("SELECT id FROM installments WHERE sale_id=? AND installment_number=?",(sale_id,num)); rr=cur.fetchone(); con.close()
            if rr: mark_installment_unpaid(rr[0],detail)
        tk.Button(action_bar, text="⚠️ ثبت عدم پرداخت", command=mark_unpaid_selected, bg="#F59E0B", fg="white", relief="flat", bd=0, font=("Tahoma",10,"bold"), cursor="hand2").pack(side="right", padx=5, ipadx=18, ipady=7)


def sales_history_window():
    if not require_permission("history", window): return

    history = tk.Toplevel(window)
    history.title("تاریخچه فروش")
    history.geometry("1250x720")
    history.minsize(1050, 620)
    history.configure(bg="#F4F6F8")

    tk.Label(history, text="📋 تاریخچه فروش", font=("Tahoma", 20, "bold"),
             bg="#111827", fg="white", height=2).pack(fill="x")
    main = tk.Frame(history, bg="#F4F6F8")
    main.pack(fill="both", expand=True, padx=25, pady=25)
    tree = ttk.Treeview(main, columns=("id", "customer", "date", "type", "cash", "total", "down", "remain", "count"),
                        show="headings", selectmode="browse")
    headings = {"id":"شماره فروش", "customer":"مشتری", "date":"تاریخ", "type":"نوع پرداخت",
                "cash":"قیمت نقدی", "total":"مبلغ نهایی", "down":"پیش‌پرداخت", "remain":"باقی‌مانده", "count":"تعداد اقساط"}
    for col, heading in headings.items():
        tree.heading(col, text=heading)
        tree.column(col, width=120, anchor="center")
    tree.column("customer", width=180, anchor="e")
    tree.pack(fill="both", expand=True)
    scroll = ttk.Scrollbar(main, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")

    def load():
        for item in tree.get_children(): tree.delete(item)
        con = connect_database(); cur = con.cursor()
        cur.execute("""
            SELECT s.id, COALESCE(c.name, '-'), s.sale_date, s.payment_type,
                   COALESCE(s.cash_total, s.total_amount), s.total_amount,
                   COALESCE(s.down_payment, s.paid_amount), s.remaining_amount,
                   COALESCE(s.installment_count, 0)
            FROM sales s LEFT JOIN customers c ON c.id=s.customer_id
            ORDER BY s.id DESC
        """)
        rows = cur.fetchall(); con.close()
        for r in rows:
            tree.insert("", "end", iid=str(r[0]), values=(r[0], r[1], display_sale_date(r[2]), r[3], f"{r[4]:,}",
                                                             f"{r[5]:,}", f"{r[6]:,}", f"{r[7]:,}", r[8]))
    def open_selected(event=None):
        sel = tree.selection()
        if sel: sale_detail_window(int(sel[0]), history)
    tree.bind("<Double-1>", open_selected)
    tk.Button(history, text="👁️ مشاهده جزئیات فروش", command=open_selected, bg="#4F46E5", fg="white",
              relief="flat", bd=0, font=("Tahoma", 10, "bold"), cursor="hand2").pack(pady=(0, 20), ipadx=20, ipady=7)
    load()


def customer_profile_window(customer_id, parent=None):

    profile = tk.Toplevel(parent or window)
    profile.title("پرونده مشتری")
    profile.geometry("1150x760")
    profile.minsize(950, 650)
    profile.configure(bg="#F4F6F8")

    con = connect_database(); cur = con.cursor()
    cur.execute("SELECT id, name, phone, national_id, address, notes FROM customers WHERE id=?", (customer_id,))
    customer = cur.fetchone()
    if not customer:
        con.close(); profile.destroy(); return
    cur.execute("""
        SELECT id, sale_date, payment_type, COALESCE(cash_total,total_amount), total_amount,
               COALESCE(down_payment,paid_amount), remaining_amount, COALESCE(installment_count,0)
        FROM sales WHERE customer_id=? ORDER BY id DESC
    """, (customer_id,))
    sales = cur.fetchall()
    cur.execute("""
        SELECT COALESCE(SUM(remaining_amount),0) FROM sales WHERE customer_id=?
    """, (customer_id,))
    debt = cur.fetchone()[0]
    con.close()

    tk.Label(profile, text="👤 پرونده مشتری", font=("Tahoma", 20, "bold"), bg="#111827", fg="white", height=2).pack(fill="x")
    card = tk.Frame(profile, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    card.pack(fill="x", padx=25, pady=20)
    text = (f"نام: {customer[1]}    |    تماس: {customer[2] or '-'}    |    کد ملی: {customer[3] or '-'}\n"
            f"آدرس: {customer[4] or '-'}\nتوضیحات: {customer[5] or '-'}\n"
            f"جمع بدهی ثبت‌شده: {debt:,} تومان")
    tk.Label(card, text=text, justify="right", anchor="e", font=("Tahoma", 10, "bold"), bg="white", fg="#374151", padx=20, pady=15).pack(fill="x")
    frame = tk.Frame(profile, bg="white", highlightbackground="#E5E7EB", highlightthickness=1)
    frame.pack(fill="both", expand=True, padx=25, pady=(0, 20))
    tree = ttk.Treeview(frame, columns=("id","date","type","cash","total","down","remain","count"), show="headings")
    heads = {"id":"فروش", "date":"تاریخ", "type":"نوع", "cash":"قیمت نقدی", "total":"مبلغ نهایی", "down":"پیش‌پرداخت", "remain":"باقی‌مانده", "count":"اقساط"}
    for c,h in heads.items():
        tree.heading(c,text=h); tree.column(c,width=125,anchor="center")
    for r in sales:
        tree.insert("","end",iid=str(r[0]),values=(r[0],r[1],r[2],f"{r[3]:,}",f"{r[4]:,}",f"{r[5]:,}",f"{r[6]:,}",r[7]))
    tree.pack(fill="both",expand=True,padx=15,pady=15)
    def open_sale(event=None):
        sel=tree.selection()
        if sel: sale_detail_window(int(sel[0]), profile)
    tree.bind("<Double-1>",open_sale)

    inst_frame = tk.Frame(profile, bg="white", highlightbackground="#C7D2FE", highlightthickness=1)
    inst_frame.pack(fill="both", expand=True, padx=25, pady=(0, 20))
    tk.Label(inst_frame, text="💳 اقساط مشتری", font=("Tahoma", 12, "bold"), bg="white", fg="#3730A3").pack(anchor="e", padx=15, pady=10)
    inst_tree = ttk.Treeview(inst_frame, columns=("id","sale","num","due","amount","paid","remain","status"), show="headings", selectmode="browse")
    for c,h,w in [("id","شناسه",70),("sale","فروش",70),("num","قسط",70),("due","سررسید شمسی",130),("amount","مبلغ",130),("paid","پرداخت",130),("remain","مانده",130),("status","وضعیت",130)]:
        inst_tree.heading(c,text=h); inst_tree.column(c,width=w,anchor="center")
    inst_tree.pack(fill="both",expand=True,padx=15,pady=(0,10))
    con=connect_database(); cur=con.cursor()
    cur.execute("""SELECT i.id,i.sale_id,i.installment_number,i.due_date,i.amount,i.paid_amount,i.status
                   FROM installments i JOIN sales s ON s.id=i.sale_id WHERE s.customer_id=? ORDER BY i.due_date,i.installment_number""",(customer_id,))
    inst_rows=cur.fetchall(); con.close()
    for r in inst_rows:
        st=due_status(r[3],r[5],r[4]); rem=max(0,r[4]-r[5])
        inst_tree.insert("","end",iid=str(r[0]),values=(r[0],r[1],r[2],display_due_date(r[3]),f"{r[4]:,}",f"{r[5]:,}",f"{rem:,}",st))
    pay_bar=tk.Frame(inst_frame,bg="white"); pay_bar.pack(fill="x",padx=15,pady=(0,15))
    def pay_customer_installment():
        sel=inst_tree.selection()
        if not sel: messagebox.showwarning("انتخاب قسط","یک قسط را انتخاب کنید.",parent=profile); return
        record_installment_payment(int(sel[0]), profile)
    tk.Button(pay_bar,text="💳 ثبت/تکمیل پرداخت قسط",command=pay_customer_installment,bg="#16A34A",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold"),cursor="hand2").pack(side="right",ipadx=20,ipady=7)
    tk.Button(pay_bar,text="🧾 فاکتور فروش",command=lambda: (sale_detail_window(int(tree.selection()[0]), profile) if tree.selection() else messagebox.showwarning("انتخاب فروش","یک فروش را انتخاب کنید.",parent=profile)),bg="#4F46E5",fg="white",relief="flat",bd=0,font=("Tahoma",10,"bold"),cursor="hand2").pack(side="right",padx=8,ipadx=20,ipady=7)


# ==================================================
# CUSTOMER MANAGEMENT
# ==================================================

def customer_management_window():
    if not require_permission("customers", window): return

    customer_window = tk.Toplevel(window)

    customer_window.title("مدیریت مشتریان")
    customer_window.geometry("1250x720")
    customer_window.minsize(1050, 650)
    customer_window.configure(bg="#F4F6F8")


    # ==================================================
    # HEADER
    # ==================================================

    header = tk.Frame(
        customer_window,
        bg="#111827",
        height=105
    )

    header.pack(
        fill="x"
    )

    header.pack_propagate(False)


    icon_label = tk.Label(
        header,
        text="👥",
        font=("Tahoma", 30),
        bg="#111827",
        fg="white"
    )

    icon_label.pack(
        side="right",
        padx=(20, 35),
        pady=20
    )


    header_text = tk.Frame(
        header,
        bg="#111827"
    )

    header_text.pack(
        side="right",
        pady=18
    )


    title_label = tk.Label(
        header_text,
        text="مدیریت مشتریان",
        font=("Tahoma", 20, "bold"),
        bg="#111827",
        fg="white"
    )

    title_label.pack(
        anchor="e"
    )


    subtitle_label = tk.Label(
        header_text,
        text="افزودن، ویرایش، حذف و جستجوی مشتریان",
        font=("Tahoma", 10),
        bg="#111827",
        fg="#CBD5E1"
    )

    subtitle_label.pack(
        anchor="e",
        pady=(4, 0)
    )


    # ==================================================
    # MAIN
    # ==================================================

    main_frame = tk.Frame(
        customer_window,
        bg="#F4F6F8"
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=30,
        pady=25
    )


    # ==================================================
    # TOOLBAR
    # ==================================================

    toolbar = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    toolbar.pack(
        fill="x",
        pady=(0, 15)
    )


    # ==================================================
    # SEARCH
    # ==================================================

    search_area = tk.Frame(
        toolbar,
        bg="white"
    )

    search_area.pack(
        side="right",
        padx=15,
        pady=12
    )


    search_icon = tk.Label(
        search_area,
        text="🔍",
        font=("Tahoma", 16),
        bg="white"
    )

    search_icon.pack(
        side="right",
        padx=(0, 8)
    )


    search_var = tk.StringVar()


    search_entry = tk.Entry(
        search_area,
        textvariable=search_var,
        font=("Tahoma", 11),
        width=35,
        justify="right",
        relief="flat",
        bd=0,
        bg="#F3F4F6"
    )

    search_entry.pack(
        side="right",
        ipady=8
    )


    # ==================================================
    # ACTION BUTTONS
    # ==================================================

    action_area = tk.Frame(
        toolbar,
        bg="white"
    )

    action_area.pack(
        side="left",
        padx=15,
        pady=10
    )


    def action_button(
        text,
        bg,
        hover_bg,
        command
    ):

        button = tk.Button(
            action_area,
            text=text,
            font=("Tahoma", 10, "bold"),
            bg=bg,
            fg="#1F2937",
            activebackground=hover_bg,
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            width=13,
            command=command
        )

        button.pack(
            side="left",
            padx=4,
            ipady=6
        )


        def enter(event):

            button.configure(
                bg=hover_bg,
                fg="white"
            )


        def leave(event):

            button.configure(
                bg=bg,
                fg="#1F2937"
            )


        button.bind(
            "<Enter>",
            enter
        )

        button.bind(
            "<Leave>",
            leave
        )


        return button


    # ==================================================
    # TABLE HEADER
    # ==================================================

    table_header = tk.Frame(
        main_frame,
        bg="#F4F6F8"
    )

    table_header.pack(
        fill="x",
        pady=(0, 10)
    )


    table_title = tk.Label(
        table_header,
        text="👥 فهرست مشتریان",
        font=("Tahoma", 14, "bold"),
        bg="#F4F6F8",
        fg="#111827"
    )

    table_title.pack(
        side="right"
    )


    result_count = tk.Label(
        table_header,
        text="۰ مشتری",
        font=("Tahoma", 10),
        bg="#E5E7EB",
        fg="#4B5563",
        padx=12,
        pady=5
    )

    result_count.pack(
        side="left"
    )


    # ==================================================
    # TABLE CARD
    # ==================================================

    table_card = tk.Frame(
        main_frame,
        bg="white",
        highlightthickness=1,
        highlightbackground="#E5E7EB"
    )

    table_card.pack(
        fill="both",
        expand=True
    )


    table_frame = tk.Frame(
        table_card,
        bg="white"
    )

    table_frame.pack(
        fill="both",
        expand=True,
        padx=15,
        pady=15
    )


    # ==================================================
    # TREEVIEW STYLE
    # ==================================================

    style = ttk.Style()


    style.configure(
        "Customer.Treeview",
        font=("Tahoma", 10),
        rowheight=38,
        background="white",
        fieldbackground="white",
        foreground="#1F2937"
    )


    style.configure(
        "Customer.Treeview.Heading",
        font=("Tahoma", 10, "bold"),
        background="#F3F4F6",
        foreground="#111827",
        padding=8
    )


    style.map(
        "Customer.Treeview",
        background=[
            ("selected", "#E0E7FF")
        ],
        foreground=[
            ("selected", "#111827")
        ]
    )


    # ==================================================
    # COLUMNS
    # ==================================================

    columns = (
        "name",
        "phone",
        "national_id",
        "address",
        "notes"
    )


    customer_tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        style="Customer.Treeview",
        selectmode="browse"
    )


    headings = {

        "name": "نام مشتری",

        "phone": "شماره تماس",

        "national_id": "کد ملی",

        "address": "آدرس",

        "notes": "توضیحات"

    }


    for column, heading in headings.items():

        customer_tree.heading(
            column,
            text=heading
        )


    widths = {

        "name": 180,

        "phone": 140,

        "national_id": 140,

        "address": 350,

        "notes": 250

    }


    for column, width in widths.items():

        customer_tree.column(
            column,
            width=width,
            minwidth=80,
            anchor="center"
        )


    customer_tree.column(
        "name",
        anchor="e"
    )


    customer_tree.column(
        "address",
        anchor="e"
    )


    customer_tree.column(
        "notes",
        anchor="e"
    )


    # ==================================================
    # SCROLLBARS
    # ==================================================

    scrollbar_y = ttk.Scrollbar(
        table_frame,
        orient="vertical",
        command=customer_tree.yview
    )


    scrollbar_x = ttk.Scrollbar(
        table_frame,
        orient="horizontal",
        command=customer_tree.xview
    )


    customer_tree.configure(
        yscrollcommand=scrollbar_y.set,
        xscrollcommand=scrollbar_x.set
    )


    customer_tree.grid(
        row=0,
        column=0,
        sticky="nsew"
    )


    scrollbar_y.grid(
        row=0,
        column=1,
        sticky="ns"
    )


    scrollbar_x.grid(
        row=1,
        column=0,
        sticky="ew"
    )


    table_frame.rowconfigure(
        0,
        weight=1
    )


    table_frame.columnconfigure(
        0,
        weight=1
    )


    # ==================================================
    # LOAD CUSTOMERS
    # ==================================================

    def load_customers():

        for item in customer_tree.get_children():

            customer_tree.delete(item)


        connection = connect_database()

        cursor = connection.cursor()


        cursor.execute("""
            SELECT
                id,
                name,
                phone,
                national_id,
                address,
                notes
            FROM customers
            ORDER BY id DESC
        """)


        customers = cursor.fetchall()

        connection.close()


        for customer in customers:

            customer_tree.insert(
                "",
                "end",
                iid=str(customer[0]),
                values=(
                    customer[1],
                    customer[2] or "",
                    customer[3] or "",
                    customer[4] or "",
                    customer[5] or ""
                )
            )


        result_count.config(
            text=f"{len(customers):,} مشتری"
        )


    # ==================================================
    # SEARCH CUSTOMERS
    # ==================================================

    def search_customers(*args):

        text = search_var.get().strip()


        for item in customer_tree.get_children():

            customer_tree.delete(item)


        connection = connect_database()

        cursor = connection.cursor()


        if text:

            search_value = f"%{text}%"


            cursor.execute("""
                SELECT
                    id,
                    name,
                    phone,
                    national_id,
                    address,
                    notes
                FROM customers
                WHERE name LIKE ?
                   OR phone LIKE ?
                   OR national_id LIKE ?
                ORDER BY id DESC
            """, (
                search_value,
                search_value,
                search_value
            ))


        else:

            cursor.execute("""
                SELECT
                    id,
                    name,
                    phone,
                    national_id,
                    address,
                    notes
                FROM customers
                ORDER BY id DESC
            """)


        customers = cursor.fetchall()

        connection.close()


        for customer in customers:

            customer_tree.insert(
                "",
                "end",
                iid=str(customer[0]),
                values=(
                    customer[1],
                    customer[2] or "",
                    customer[3] or "",
                    customer[4] or "",
                    customer[5] or ""
                )
            )


        result_count.config(
            text=f"{len(customers):,} مشتری"
        )


    # ==================================================
    # ADD CUSTOMER
    # ==================================================

    def add_customer():

        add_window = tk.Toplevel(
            customer_window
        )

        add_window.title(
            "افزودن مشتری"
        )

        add_window.geometry(
            "550x560"
        )

        add_window.resizable(
            False,
            False
        )

        add_window.configure(
            bg="#F4F6F8"
        )


        title = tk.Label(
            add_window,
            text="➕ افزودن مشتری جدید",
            font=("Tahoma", 18, "bold"),
            bg="#111827",
            fg="white"
        )

        title.pack(
            fill="x",
            pady=20
        )


        form = tk.Frame(
            add_window,
            bg="white"
        )

        form.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )


        name_var = tk.StringVar()

        phone_var = tk.StringVar()

        national_id_var = tk.StringVar()

        address_var = tk.StringVar()

        notes_var = tk.StringVar()


        def field(
            row,
            text,
            variable
        ):

            label = tk.Label(
                form,
                text=text,
                font=("Tahoma", 10, "bold"),
                bg="white",
                fg="#374151",
                width=12,
                anchor="e"
            )

            label.grid(
                row=row,
                column=1,
                padx=10,
                pady=9
            )


            entry = tk.Entry(
                form,
                textvariable=variable,
                font=("Tahoma", 10),
                justify="right",
                width=35
            )

            entry.grid(
                row=row,
                column=0,
                padx=10,
                pady=9,
                ipady=5
            )


            return entry


        name_entry = field(
            0,
            "نام مشتری:",
            name_var
        )


        field(
            1,
            "شماره تماس:",
            phone_var
        )


        field(
            2,
            "کد ملی:",
            national_id_var
        )


        field(
            3,
            "آدرس:",
            address_var
        )


        field(
            4,
            "توضیحات:",
            notes_var
        )


        def save_customer():

            name = name_var.get().strip()

            phone = phone_var.get().strip()

            national_id = national_id_var.get().strip()

            address = address_var.get().strip()

            notes = notes_var.get().strip()


            if not name:

                messagebox.showerror(
                    "خطا",
                    "نام مشتری نمی‌تواند خالی باشد.",
                    parent=add_window
                )

                name_entry.focus()

                return


            connection = connect_database()

            cursor = connection.cursor()


            try:

                cursor.execute("""
                    INSERT INTO customers
                    (
                        name,
                        phone,
                        national_id,
                        address,
                        notes
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name,
                    phone,
                    national_id,
                    address,
                    notes
                ))


                connection.commit()


                messagebox.showinfo(
                    "موفق",
                    "مشتری با موفقیت اضافه شد.",
                    parent=add_window
                )


                add_window.destroy()

                load_customers()


            finally:

                connection.close()


        save_button = tk.Button(
            add_window,
            text="💾 ذخیره مشتری",
            font=("Tahoma", 11, "bold"),
            bg="#4F46E5",
            fg="white",
            activebackground="#4338CA",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            width=18,
            command=save_customer
        )

        save_button.pack(
            pady=(0, 25),
            ipady=7
        )


        name_entry.focus()


    # ==================================================
    # EDIT CUSTOMER
    # ==================================================

    def edit_customer():

        selected = customer_tree.selection()


        if not selected:

            messagebox.showwarning(
                "انتخاب مشتری",
                "ابتدا یک مشتری را از جدول انتخاب کنید.",
                parent=customer_window
            )

            return


        customer_id = selected[0]


        connection = connect_database()

        cursor = connection.cursor()


        cursor.execute("""
            SELECT
                name,
                phone,
                national_id,
                address,
                notes
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        ))


        customer = cursor.fetchone()

        connection.close()


        if customer is None:

            messagebox.showerror(
                "خطا",
                "مشتری پیدا نشد.",
                parent=customer_window
            )

            return


        edit_window = tk.Toplevel(
            customer_window
        )

        edit_window.title(
            "ویرایش مشتری"
        )

        edit_window.geometry(
            "550x560"
        )

        edit_window.resizable(
            False,
            False
        )

        edit_window.configure(
            bg="#F4F6F8"
        )


        title = tk.Label(
            edit_window,
            text="✏️ ویرایش مشتری",
            font=("Tahoma", 18, "bold"),
            bg="#111827",
            fg="white"
        )

        title.pack(
            fill="x",
            pady=20
        )


        form = tk.Frame(
            edit_window,
            bg="white"
        )

        form.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )


        name_var = tk.StringVar(
            value=customer[0]
        )

        phone_var = tk.StringVar(
            value=customer[1] or ""
        )

        national_id_var = tk.StringVar(
            value=customer[2] or ""
        )

        address_var = tk.StringVar(
            value=customer[3] or ""
        )

        notes_var = tk.StringVar(
            value=customer[4] or ""
        )


        def field(
            row,
            text,
            variable
        ):

            label = tk.Label(
                form,
                text=text,
                font=("Tahoma", 10, "bold"),
                bg="white",
                fg="#374151",
                width=12,
                anchor="e"
            )

            label.grid(
                row=row,
                column=1,
                padx=10,
                pady=9
            )


            entry = tk.Entry(
                form,
                textvariable=variable,
                font=("Tahoma", 10),
                justify="right",
                width=35
            )

            entry.grid(
                row=row,
                column=0,
                padx=10,
                pady=9,
                ipady=5
            )


            return entry


        name_entry = field(
            0,
            "نام مشتری:",
            name_var
        )


        field(
            1,
            "شماره تماس:",
            phone_var
        )


        field(
            2,
            "کد ملی:",
            national_id_var
        )


        field(
            3,
            "آدرس:",
            address_var
        )


        field(
            4,
            "توضیحات:",
            notes_var
        )


        def update_customer():

            name = name_var.get().strip()

            phone = phone_var.get().strip()

            national_id = national_id_var.get().strip()

            address = address_var.get().strip()

            notes = notes_var.get().strip()


            if not name:

                messagebox.showerror(
                    "خطا",
                    "نام مشتری نمی‌تواند خالی باشد.",
                    parent=edit_window
                )

                name_entry.focus()

                return


            connection = connect_database()

            cursor = connection.cursor()


            cursor.execute("""
                UPDATE customers
                SET
                    name = ?,
                    phone = ?,
                    national_id = ?,
                    address = ?,
                    notes = ?
                WHERE id = ?
            """, (
                name,
                phone,
                national_id,
                address,
                notes,
                customer_id
            ))


            connection.commit()

            connection.close()


            messagebox.showinfo(
                "موفق",
                "اطلاعات مشتری با موفقیت ویرایش شد.",
                parent=edit_window
            )


            edit_window.destroy()

            load_customers()


        save_button = tk.Button(
            edit_window,
            text="💾 ذخیره تغییرات",
            font=("Tahoma", 11, "bold"),
            bg="#4F46E5",
            fg="white",
            activebackground="#4338CA",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            width=18,
            command=update_customer
        )

        save_button.pack(
            pady=(0, 25),
            ipady=7
        )


        name_entry.focus()


    # ==================================================
    # DELETE CUSTOMER
    # ==================================================

    def delete_customer():

        selected = customer_tree.selection()


        if not selected:

            messagebox.showwarning(
                "انتخاب مشتری",
                "ابتدا یک مشتری را از جدول انتخاب کنید.",
                parent=customer_window
            )

            return


        customer_id = selected[0]


        connection = connect_database()

        cursor = connection.cursor()


        cursor.execute("""
            SELECT
                name,
                phone
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        ))


        customer = cursor.fetchone()

        connection.close()


        if customer is None:

            messagebox.showerror(
                "خطا",
                "مشتری پیدا نشد.",
                parent=customer_window
            )

            return


        answer = messagebox.askyesno(
            "تأیید حذف",
            (
                "آیا مطمئن هستید که می‌خواهید این مشتری را حذف کنید؟\n\n"
                f"نام: {customer[0]}\n"
                f"شماره تماس: {customer[1] or '-'}\n\n"
                "این عملیات قابل برگشت نیست."
            ),
            parent=customer_window
        )


        if not answer:

            return


        connection = connect_database()

        cursor = connection.cursor()


        try:

            cursor.execute("""
                DELETE FROM customers
                WHERE id = ?
            """, (
                customer_id,
            ))


            connection.commit()


            messagebox.showinfo(
                "موفق",
                "مشتری با موفقیت حذف شد.",
                parent=customer_window
            )


            load_customers()


        finally:

            connection.close()


    # ==================================================
    # BUTTONS
    # ==================================================

    action_button(
        "➕ افزودن مشتری",
        "#ECFDF5",
        "#059669",
        add_customer
    )


    action_button(
        "✏️ ویرایش",
        "#EEF2FF",
        "#4338CA",
        edit_customer
    )


    action_button(
        "🗑️ حذف",
        "#FEF2F2",
        "#DC2626",
        delete_customer
    )


    action_button(
        "🔄 بروزرسانی",
        "#F1F5F9",
        "#475569",
        load_customers
    )


    def open_selected_customer_profile():

        selected = customer_tree.selection()
        if not selected:
            messagebox.showwarning(
                "انتخاب مشتری",
                "ابتدا یک مشتری را انتخاب کنید.",
                parent=customer_window
            )
            return

        customer_profile_window(int(selected[0]), customer_window)

    action_button(
        "📁 پرونده مشتری",
        "#EFF6FF",
        "#2563EB",
        open_selected_customer_profile
    )


    # ==================================================
    # SEARCH EVENTS
    # ==================================================

    search_var.trace_add(
        "write",
        search_customers
    )


    search_entry.bind(
        "<Return>",
        search_customers
    )


    # ==================================================
    # DOUBLE CLICK EDIT
    # ==================================================

    customer_tree.bind(
        "<Double-1>",
        lambda event: edit_customer()
    )


    # ==================================================
    # ESCAPE
    # ==================================================

    customer_window.bind(
        "<Escape>",
        lambda event: customer_window.destroy()
    )


    # ==================================================
    # INITIAL LOAD
    # ==================================================

    load_customers()

    search_entry.focus()


# ==================================================
# DASHBOARD
# ==================================================

create_modern_button(
    buttons_frame,
    "داشبورد",
    "📊",
    "#EEF2FF",
    PRIMARY,
    dashboard_window,
    0,
    0
)


# ==================================================
# ADD PRODUCT
# ==================================================

create_modern_button(
    buttons_frame,
    "افزودن کالا",
    "➕",
    "#ECFDF5",
    GREEN,
    add_product_window,
    0,
    1
)


# ==================================================
# INVENTORY
# ==================================================

create_modern_button(
    buttons_frame,
    "موجودی کالاها",
    "📦",
    "#EFF6FF",
    BLUE,
    show_inventory,
    0,
    2
)


# ==================================================
# SEARCH
# ==================================================

create_modern_button(
    buttons_frame,
    "جستجوی کالا",
    "🔍",
    "#F5F3FF",
    PURPLE,
    search_product_window,
    0,
    3
)


# ==================================================
# STOCK IN
# ==================================================

create_modern_button(
    buttons_frame,
    "ورود کالا",
    "📥",
    "#ECFDF5",
    GREEN,
    lambda: stock_movement_window("ورود"),
    1,
    0
)


# ==================================================
# STOCK OUT
# ==================================================

create_modern_button(
    buttons_frame,
    "خروج کالا",
    "📤",
    "#FFF7ED",
    ORANGE,
    lambda: stock_movement_window("خروج"),
    1,
    1
)


# ==================================================
# HISTORY
# ==================================================

create_modern_button(
    buttons_frame,
    "تاریخچه عملیات",
    "📋",
    "#F8FAFC",
    "#475569",
    history_window,
    1,
    2
)

# ==================================================
# CUSTOMERS
# ==================================================

create_modern_button(
    buttons_frame,
    "مدیریت مشتریان",
    "👤",
    "#EFF6FF",
    BLUE,
    customer_management_window,
    1,
    3
)

# ==================================================
# SALES
# ==================================================

create_modern_button(
    buttons_frame,
    "فروش",
    "🛒",
    "#FFF7ED",
    ORANGE,
    sales_window,
    2,
    0
)


# ==================================================
# CATEGORY / BRAND MANAGEMENT
# ==================================================

create_modern_button(
    buttons_frame,
    "برند و دسته‌بندی",
    "⚙️",
    "#F1F5F9",
    "#334155",
    manage_categories_brands,
    2,
    1
)


# ==================================================
# USERS
# ==================================================

if has_permission("all"):
    create_modern_button(
        buttons_frame,
        "مدیریت کاربران",
        "👥",
        "#F3E8FF",
        PURPLE,
        user_management_window,
        2,
        2
    )

    create_modern_button(
        buttons_frame,
        "پشتیبان‌گیری",
        "💾",
        "#ECFDF5",
        GREEN,
        backup_database,
        3,
        2
    )

# ابزارهای عمومی متناسب با سطح دسترسی
if has_permission("reports"):
    create_modern_button(buttons_frame,"گزارش‌های مالی","📊","#EEF2FF",PRIMARY,reports_window,3,0)
if CURRENT_USER:
    create_modern_button(buttons_frame,"تغییر رمز","🔑","#FEF3C7","#92400E",change_password_window,3,1)
if has_permission("settings"):
    create_modern_button(buttons_frame,"تنظیمات فروشگاه","⚙️","#F1F5F9","#334155",settings_window,3,3)
create_modern_button(buttons_frame,"خروج از حساب","🚪","#FEE2E2","#B91C1C",logout_and_relogin,4,3)

# ==================================================
# SALES HISTORY
# ==================================================

if has_permission("history"):
    create_modern_button(
        buttons_frame,
        "تاریخچه فروش",
        "🧾",
        "#EFF6FF",
        BLUE,
        sales_history_window,
        2,
        3
    )


# ==================================================
# INFORMATION PANEL
# ==================================================

info_frame = tk.Frame(
    content,
    bg=WHITE,
    highlightbackground=BORDER,
    highlightthickness=1
)

info_frame.pack(
    fill="x",
    pady=(30, 0)
)


info_inner = tk.Frame(
    info_frame,
    bg=WHITE
)

info_inner.pack(
    fill="x",
    padx=25,
    pady=20
)


# -----------------------------
# Information right
# -----------------------------

info_right = tk.Frame(
    info_inner,
    bg=WHITE
)

info_right.pack(
    side="right"
)


info_icon = tk.Label(
    info_right,
    text="💡",
    font=("Tahoma", 24),
    bg=WHITE
)

info_icon.pack(
    side="right",
    padx=(0, 12)
)


info_text = tk.Frame(
    info_right,
    bg=WHITE
)

info_text.pack(
    side="right"
)


info_title = tk.Label(
    info_text,
    text="مدیریت سریع‌تر، کنترل بهتر",
    font=("Tahoma", 12, "bold"),
    bg=WHITE,
    fg=TEXT_DARK
)

info_title.pack(
    anchor="e"
)


info_description = tk.Label(
    info_text,
    text="از منوی بالا برای مدیریت کالاها، موجودی و عملیات انبار استفاده کنید.",
    font=("Tahoma", 9),
    bg=WHITE,
    fg=TEXT_GRAY
)

info_description.pack(
    anchor="e",
    pady=(4, 0)
)


# -----------------------------
# Information left
# -----------------------------

info_left = tk.Frame(
    info_inner,
    bg=WHITE
)

info_left.pack(
    side="left"
)


database_status = tk.Label(
    info_left,
    text="● پایگاه داده متصل است",
    font=("Tahoma", 9, "bold"),
    bg=WHITE,
    fg=GREEN
)

database_status.pack()


# ==================================================
# FOOTER
# ==================================================

footer = tk.Frame(
    window,
    bg=WHITE,
    height=45
)

footer.pack(
    fill="x",
    side="bottom"
)

footer.pack_propagate(False)


footer_label = tk.Label(
    footer,
    text="سیستم مدیریت موجودی فروشگاه  •  نسخه نهایی 2.0",
    font=("Tahoma", 9),
    bg=WHITE,
    fg=TEXT_GRAY
)

footer_label.pack(
    pady=13
)


# ==================================================
# START
# ==================================================

window.mainloop()