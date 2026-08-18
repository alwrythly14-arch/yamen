import streamlit as st
import pandas as pd
import psycopg2
import requests
import os
import json
import uuid
import base64
from datetime import datetime
from dotenv import load_dotenv

# مكتبات الربط مع Google Sheets (جديد): gspread للاتصال بالـ API، و
# gspread-dataframe لتحويل الشيت من/إلى DataFrame بسهولة حتى يقدر
# st.data_editor يتعامل معه مباشرة (عرض + تعديل + إضافة/حذف صفوف)
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# تحميل بيانات الاتصال من ملف .env (يجب إنشاؤه بجانب هذا الملف، راجع .env.example)
# override=True يضمن قراءة آخر تعديل بالملف حتى لو تغيّر بعد أول تشغيل
load_dotenv(override=True)

# ============================================================
# 1) إعدادات الصفحة العامة
# ============================================================
st.set_page_config(
    page_title="لوحة تحكم الوكيل الذكي",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 2) التصميم المتطور (CSS مخصص + دعم الاتجاه من اليمين لليسار)
# ملاحظة: كل هذا القسم "تجميلي" فقط ولا يؤثر على منطق البرنامج
# ============================================================
st.markdown("""
<style>
    html, body, .stApp {
        direction: RTL;
        font-family: 'Tajawal', 'Segoe UI', sans-serif;
    }
    /* محاذاة النصوص لليمين بدون قلب اتجاه العناصر الداخلية للمكوّنات
       (كان هذا سبب خروج مؤشر زر التفعيل Toggle خارج صندوقه) */
    p, h1, h2, h3, h4, h5, h6, label, span, li,
    div[data-testid="stMarkdownContainer"] {
        text-align: right;
    }

    /* إرجاع اتجاه مكوّنات التحكم (زر التفعيل / القوائم المنسدلة / الأشرطة)
       إلى وضعها الطبيعي LTR حتى لا ينكسر شكلها البصري داخل صفحة RTL */
    div[data-testid="stToggle"],
    div[data-testid="stToggle"] *,
    div[data-baseweb="switch"],
    div[data-baseweb="switch"] *,
    div[data-testid="stCheckbox"] *,
    div[data-testid="stSlider"] *,
    div[data-baseweb="select"] * {
        direction: LTR;
    }
    /* لكن نص القائمة المنسدلة نفسه يبقى محاذي لليمين */
    div[data-baseweb="select"] { text-align: right; }

    /* ------------------------------------------------------------
       إصلاح: زر تصغير/توسيع القائمة الجانبية + سهم التمرير داخلها
       كانا يظهران في منتصف الشاشة بدل مكانهما الطبيعي، بسبب أن هذي
       الأزرار من Streamlit نفسه مبنية بافتراض صفحة LTR (بموضع مطلق)،
       وانعكاس اتجاه الصفحة بالكامل لـ RTL كان يكسر حساب موضعها.
       نرجعها هنا لاتجاهها الطبيعي ونثبّت موضعها يدوياً بدل ما "تتوه".
       ------------------------------------------------------------ */
    [data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"],
    div[data-testid="stSidebarCollapseButton"],
    button[kind="header"] {
        direction: LTR !important;
        position: fixed !important;
        top: 0.5rem !important;
        left: 0.5rem !important;
        right: auto !important;
        transform: none !important;
    }

    /* سهم التمرير لرؤية بقية عناصر القائمة الجانبية (يظهر لما محتوى
       القائمة يكون أطول من ارتفاع الشاشة) — نفس سبب المشكلة أعلاه */
    section[data-testid="stSidebar"] [class*="ScrollButton"],
    section[data-testid="stSidebar"] button[title*="scroll"],
    section[data-testid="stSidebar"] [data-testid*="scroll"] {
        direction: LTR !important;
        left: 50% !important;
        right: auto !important;
        transform: translateX(-50%) !important;
    }

    /* خلفية الشريط الجانبي */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

    /* عنوان الصفحة الرئيسي */
    .main-title {
        background: linear-gradient(90deg, #6366f1, #8b5cf6);
        padding: 22px 28px;
        border-radius: 18px;
        color: white;
        margin-bottom: 25px;
        box-shadow: 0 8px 20px rgba(99,102,241,0.25);
    }
    .main-title h1 { margin: 0; font-size: 26px; }
    .main-title p { margin: 4px 0 0 0; opacity: 0.9; font-size: 14px; }

    /* بطاقات المقاييس (KPIs) */
    div[data-testid="stMetric"] {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 18px;
    }
    div[data-testid="stMetricLabel"] { color: #94a3b8 !important; }
    div[data-testid="stMetricValue"] { color: #f8fafc !important; }

    /* الأزرار */
    .stButton>button {
        border-radius: 10px;
        background: linear-gradient(90deg,#6366f1,#8b5cf6);
        color: white;
        border: none;
        padding: 0.55rem 1.3rem;
        font-weight: 600;
        transition: 0.2s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 14px rgba(99,102,241,0.35);
    }

    /* حاويات البطاقات */
    .card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 3) الاتصال بقاعدة بيانات Supabase (Postgres) وإنشاء الجداول المطلوبة
# ملاحظة: البيانات الحين مخزّنة على Supabase (سحابياً)، وليست بملف
# محلي على جهازك، لكنك تقدر تفتحها وتشوفها من موقع Supabase بالكامل
# ============================================================
@st.cache_resource
def get_connection():
    new_conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSLMODE", "require"),
    )
    # نفعّل autocommit فوراً هنا (قبل أي استعلام) حتى لا نصطدم بخطأ
    # "set_session cannot be used inside a transaction" لاحقاً
    new_conn.autocommit = True
    return new_conn


def get_healthy_connection():
    """
    Supabase يقفل الاتصال تلقائياً لو ضل بدون استخدام لفترة (Idle Timeout).
    هذي الدالة تتأكد إن الاتصال المحفوظ لسا شغّال قبل استخدامه، ولو صار
    مقفول (أو صار فيه أي خطأ بالاتصال)، تفرّغ الذاكرة المؤقتة وتعيد
    الاتصال من جديد تلقائياً، بدل ما يطلع خطأ ويوقف التطبيق بالكامل.

    تحسين أداء: لا نفحص الاتصال بـ "SELECT 1" مع كل تنقل/ضغطة (هذا كان يضيف
    رحلة كاملة لقاعدة بيانات سحابية بكل حركة ويسبب بطء ملحوظ بالتنقل بين
    الصفحات)، بل نفحصه كحد أقصى مرة كل 30 ثانية فقط. لو الاتصال انقطع فعلاً
    بين الفحصين، أي استعلام عادي بيطلع خطأ واضح وقتها بدل ما يبطئ كل شي.
    """
    connection = get_connection()
    now = datetime.now()
    last_check = st.session_state.get("_last_health_check")
    if last_check is not None and (now - last_check).total_seconds() < 30:
        return connection
    try:
        # فحص بسيط وسريع: لو الاتصال ميت، هذا السطر يطلع استثناء فوراً
        test_cursor = connection.cursor()
        test_cursor.execute("SELECT 1")
        test_cursor.close()
        st.session_state["_last_health_check"] = now
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        get_connection.clear()  # نفرّغ الاتصال القديم الميت من الذاكرة المؤقتة
        connection = get_connection()  # ونسوي اتصال جديد صحي
        st.session_state["_last_health_check"] = now
    return connection


@st.cache_resource
def initialize_database_schema(_conn):
    """
    ينشئ ويعدّل كل الجداول والفهارس اللازمة لعمل التطبيق.

    مهم جداً: بفضل @st.cache_resource، هذي الدالة تنفّذ مرة وحدة بس طوال
    عمر التطبيق (أول تشغيل)، بدل ما تعيد إرسال ~10 أوامر SQL لقاعدة
    البيانات مع كل تنقل بين الصفحات أو أي ضغطة زر. هذا كان فعلياً أحد
    الأسباب الرئيسية لبطء التنقل — كل الأوامر (CREATE TABLE/ALTER/CREATE
    INDEX) كانت تُرسل من جديد لقاعدة بيانات سحابية بكل حركة، رغم إنها
    IF NOT EXISTS ولا تغيّر شي فعلياً بعد أول مرة.
    """
    c = _conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS keywords (
        id SERIAL PRIMARY KEY,
        keyword TEXT,
        active INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS news (
        title TEXT, site TEXT, url TEXT, date TEXT
    )""")
    # نضيف عمود id لو مو موجود (أمان: ما يمسح أي بيانات موجودة عندك بالجدول)
    c.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS id SERIAL")

    # فحص أمان: لو الجدول news كان موجود مسبقاً (مثلاً أنشأه n8n قبل هذا التطبيق)
    # فجملة CREATE TABLE IF NOT EXISTS اللي فوق ما تكون نفّذت شي، ويبقى عمود
    # date على نوعه الأصلي. لو كان نوعه DATE أو TIMESTAMP بدل TEXT، فـ Postgres
    # يقص أي وقت يرسله n8n تلقائياً عند كل إدخال (حتى لو النص المرسل فيه وقت
    # كامل)، وهذا هو سبب ظهور اليوم فقط بدون الوقت بالواجهة. نحوّل العمود هنا
    # تلقائياً إلى TEXT (بدون حذف أي بيانات) عشان أي وقت يرسله n8n من الآن
    # فصاعداً يتخزن كما هو بالضبط.
    c.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'news' AND column_name = 'date'
    """)
    existing_date_col_type = c.fetchone()
    if existing_date_col_type and existing_date_col_type[0] != "text":
        c.execute("ALTER TABLE news ALTER COLUMN date TYPE TEXT")

    # جدول جديد: مواقع البحث المستهدفة اللي يدور عليهم n8n
    c.execute("""CREATE TABLE IF NOT EXISTS search_sites (
        id SERIAL PRIMARY KEY,
        site_url TEXT,
        active INTEGER
    )""")

    # جدول جديد: لتسجيل كل عملية أتمتة يتم تنفيذها مع n8n
    c.execute("""CREATE TABLE IF NOT EXISTS automation_log (
        id SERIAL PRIMARY KEY,
        action TEXT,
        status TEXT,
        details TEXT,
        timestamp TEXT
    )""")

    # عمود جديد: يحدّد هل تم "الاطلاع" على هذا السجل الفاشل أو لا، بدل ما
    # نحذف السجل نهائياً عند الاطلاع (حذف نهائي كان يفقد سجل الفشل من
    # صفحة "سجل عمليات الأتمتة" ومن حساب "آخر حالة لكل رابط" بصفحة مواقع
    # البحث المستهدفة). الحين الاطلاع يُخفي التنبيه فقط، ويبقي السجل التاريخي.
    c.execute("ALTER TABLE automation_log ADD COLUMN IF NOT EXISTS acknowledged INTEGER DEFAULT 0")

    # فهارس لتسريع استعلامات لوحة التنبيهات والحالة (خصوصاً مع تراكم السجلات
    # بمرور الوقت) — بدونها، كل فلترة على status أو action تعمل مسحاً كاملاً
    # للجدول (Full Table Scan) وتصير أبطأ كل ما زادت السجلات
    c.execute("CREATE INDEX IF NOT EXISTS idx_automation_log_status ON automation_log (status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_automation_log_action ON automation_log (action)")

    # جدول جديد: إعدادات التطبيق (روابط n8n وغيرها) — يخزّن كـ key/value
    # بدل ما تكون الروابط مكتوبة يدوياً بكل صفحة أو معتمدة على ملف .env فقط.
    # هذا يخلي التعديل مركزي من صفحة "الإعدادات" ويبقى محفوظ بقاعدة البيانات
    # (يعني ما يروح لو التطبيق أعيد نشره أو تغيّر مكان استضافته)
    c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.close()
    return True


conn = get_healthy_connection()
initialize_database_schema(conn)
cursor = conn.cursor()


# ============================================================
# 3ب) دوال الإعدادات (روابط n8n المخزّنة بقاعدة البيانات)
# ------------------------------------------------------------
# الفكرة: بدل ما يكون كل رابط Webhook حقل نص مفتوح بكل صفحة (أي زائر
# يقدر يبدّله بنفسه ويوجّه التطبيق لرابط ثاني — ثغرة أمنية)، صارت الروابط
# تُقرأ من جدول app_settings فقط، وتُعدَّل حصرياً من صفحة "⚙️ الإعدادات".
#
# عند أول تشغيل بعد هذا التحديث، الجدول يكون فاضي، فالدوال ترجع القيمة
# الافتراضية من متغيرات البيئة (.env) إن وُجدت، أو نص فاضي إن ما وُجدت.
# لازم تدخل صفحة الإعدادات مرة وحدة بعد النشر وتتأكد إن الروابط مكتوبة
# صح ومحفوظة (خصوصاً رابط n8n Cloud الجديد بعد ما تنقل).
# ============================================================

DEFAULT_SETTINGS = {
    "ai_assistant_webhook": os.getenv("N8N_AI_ASSISTANT_WEBHOOK", ""),
    # معرّف/رابط شيت قوقل الافتراضي (اختياري) — يقدر يُترك فاضي ويُدخل لاحقاً من صفحة الإعدادات
    "google_sheet_id": os.getenv("GOOGLE_SHEET_ID", ""),
}


@st.cache_data(ttl=5, show_spinner=False)
def get_all_settings(_conn):
    """يجيب كل الإعدادات المحفوظة بقاعدة البيانات كقاموس واحد (مخزّن مؤقتاً 5 ثواني)"""
    df = pd.read_sql_query("SELECT key, value FROM app_settings", _conn)
    return dict(zip(df["key"], df["value"]))


def get_setting(key: str) -> str:
    """يرجع قيمة إعداد معين: من قاعدة البيانات إن كانت محفوظة، وإلا من .env كافتراضي"""
    saved = get_all_settings(conn)
    if key in saved and saved[key]:
        return saved[key]
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str):
    """يحفظ (أو يحدّث) قيمة إعداد معين بقاعدة البيانات"""
    cursor.execute(
        """INSERT INTO app_settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        (key, value)
    )
    get_all_settings.clear()


# ============================================================
# 3ج) الاتصال بـ Google Sheets (عرض وتعديل شيت خارجي داخل التطبيق)
# ------------------------------------------------------------
# يعتمد على "حساب خدمة" (Service Account) من Google Cloud، بدل ما يطلب
# من كل زائر يسجّل دخول بحسابه الشخصي بقوقل. تشارك الشيت مع بريد الحساب
# (بريد ينتهي بـ ...gserviceaccount.com) كـ "محرر Editor" مرة وحدة بس من
# صفحة مشاركة الشيت بقوقل، وبعدها التطبيق يقدر يقرأ ويكتب بالشيت مباشرة
# — بدون أي تسجيل دخول من المستخدم اللي يفتح موقعك (نفس فكرة إن الحساب
# "محفوظ" اللي سألت عنها: ما فيه تسجيل دخول من الأساس لأي زائر).
#
# بيانات الاعتماد تُقرأ من .env بطريقتين (يكفي وجود واحدة منهم):
#   GOOGLE_SERVICE_ACCOUNT_FILE = مسار لملف JSON (نزّلته من Google Cloud) على القرص
#   GOOGLE_SERVICE_ACCOUNT_JSON = نفس محتوى ملف الـ JSON لكن كنص كامل داخل
#                                 متغير البيئة (مفيد لو الاستضافة ما تسمح
#                                 برفع ملفات، مثل بعض منصات النشر السحابية)
#
# رابط/معرّف الشيت نفسه يُحفظ بجدول app_settings مثل رابط n8n بالضبط،
# ويُعدَّل من صفحة "⚙️ الإعدادات" — ما يحتاج تعديل بالكود.
# ============================================================

GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def get_gsheet_client():
    """ينشئ عميل Google Sheets مرة وحدة فقط طوال عمر التطبيق (نفس أسلوب get_connection).
    يرجع None لو ما فيه بيانات اعتماد بملف .env بعد (يعني الميزة مو مفعّلة لسا)."""
    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

    if json_content:
        creds_info = json.loads(json_content)
        creds = Credentials.from_service_account_info(creds_info, scopes=GOOGLE_SHEETS_SCOPES)
    elif file_path:
        creds = Credentials.from_service_account_file(file_path, scopes=GOOGLE_SHEETS_SCOPES)
    else:
        return None

    return gspread.authorize(creds)


def extract_sheet_id(sheet_url_or_id: str) -> str:
    """يقبل رابط الشيت الكامل (اللي تنسخه من المتصفح) أو المعرّف مباشرة، ويرجع المعرّف فقط"""
    value = sheet_url_or_id.strip()
    if "/d/" in value:
        return value.split("/d/")[1].split("/")[0]
    return value


def get_worksheet():
    """يرجع كائن الورقة الأولى (Worksheet) بالشيت المحفوظ بالإعدادات، مع رسالة خطأ واضحة لو فيه مشكلة"""
    client = get_gsheet_client()
    if client is None:
        return None, "بيانات اعتماد Google Service Account غير موجودة بملف .env بعد"

    sheet_ref = get_setting("google_sheet_id")
    if not sheet_ref:
        return None, "لم يتم تحديد رابط/معرّف شيت قوقل بصفحة الإعدادات بعد"

    try:
        sheet_id = extract_sheet_id(sheet_ref)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
        return worksheet, None
    except Exception as e:
        return None, f"تعذّر فتح الشيت: {e}"


# ============================================================
# 4) دوال مساعدة (Functions) — كل عملية متكررة صارت دالة مستقلة
# هذا يسهّل عليك التعديل مستقبلاً لأن كل دالة مسؤولة عن شيء واحد
# ============================================================

def add_keyword(keyword: str):
    """إضافة كلمة مفتاحية جديدة كـ (نشطة) افتراضياً"""
    cursor.execute("INSERT INTO keywords (keyword, active) VALUES (%s, 1)", (keyword,))


def keyword_exists(keyword: str) -> bool:
    """تتحقق فيما إذا كانت الكلمة المفتاحية موجودة مسبقاً (بدون حساسية لحالة الأحرف أو المسافات الزائدة)"""
    cursor.execute(
        "SELECT 1 FROM keywords WHERE LOWER(TRIM(keyword)) = LOWER(TRIM(%s)) LIMIT 1",
        (keyword,)
    )
    return cursor.fetchone() is not None


def bulk_add_keywords_callback():
    """
    يعالج الإضافة الجماعية للكلمات المفتاحية عبر نص متعدد الأسطر.
    يضيف كل كلمة غير مكررة، ويتجاهل أي كلمة موجودة مسبقاً بالجدول أو
    مكررة داخل نفس اللصق، ثم يبقي فقط الكلمات المكررة داخل الصندوق
    (يشيل الكلمات اللي انضافت بنجاح منه) عشان المستخدم يشوف وش ما انضاف.
    """
    # نجدد الاتصال بقاعدة البيانات هنا تحديداً (مو بس بأول تحميل للصفحة)،
    # لأن هذا الزر يشتغل عبر on_click، ولو المستخدم أخذ وقت وهو يلصق قائمة
    # طويلة قبل ما يضغط الزر، يكون Supabase سكّر الاتصال القديم من فترة
    # (Idle Timeout)، فنتأكد إن عندنا اتصال حي وسليم قبل أي عملية إضافة
    global conn, cursor
    conn = get_healthy_connection()
    cursor = conn.cursor()

    bulk_text = st.session_state.get("bulk_keywords_input", "")
    lines = [line.strip() for line in bulk_text.split("\n") if line.strip()]
    added_count = 0
    duplicate_lines = []
    seen_in_batch = set()
    for kw in lines:
        kw_key = kw.lower()
        if keyword_exists(kw) or kw_key in seen_in_batch:
            duplicate_lines.append(kw)
        else:
            add_keyword(kw)
            seen_in_batch.add(kw_key)
            added_count += 1
    st.session_state.bulk_keywords_input = "\n".join(duplicate_lines)
    st.session_state.bulk_kw_result = (added_count, len(duplicate_lines), len(lines) > 0)


def delete_keyword(keyword_id: int):
    """حذف كلمة مفتاحية عبر رقمها (id)"""
    cursor.execute("DELETE FROM keywords WHERE id = %s", (keyword_id,))


def toggle_keyword(keyword_id: int, new_state: int):
    """تفعيل / تعطيل كلمة مفتاحية"""
    cursor.execute("UPDATE keywords SET active = %s WHERE id = %s", (new_state, keyword_id))


def add_site(site_url: str):
    """إضافة موقع بحث مستهدف جديد كـ (نشط) افتراضياً"""
    cursor.execute("INSERT INTO search_sites (site_url, active) VALUES (%s, 1)", (site_url,))


def site_exists(site_url: str) -> bool:
    """تتحقق فيما إذا كان الموقع موجوداً مسبقاً (بدون حساسية لحالة الأحرف أو المسافات الزائدة)"""
    cursor.execute(
        "SELECT 1 FROM search_sites WHERE LOWER(TRIM(site_url)) = LOWER(TRIM(%s)) LIMIT 1",
        (site_url,)
    )
    return cursor.fetchone() is not None


def bulk_add_sites_callback():
    """نفس فكرة bulk_add_keywords_callback لكن لمواقع البحث المستهدفة"""
    # نفس التجديد للاتصال قبل الاستخدام (راجع التعليق بأعلى bulk_add_keywords_callback)
    global conn, cursor
    conn = get_healthy_connection()
    cursor = conn.cursor()

    bulk_text = st.session_state.get("bulk_sites_input", "")
    lines = [line.strip() for line in bulk_text.split("\n") if line.strip()]
    added_count = 0
    duplicate_lines = []
    seen_in_batch = set()
    for site in lines:
        site_key = site.lower()
        if site_exists(site) or site_key in seen_in_batch:
            duplicate_lines.append(site)
        else:
            add_site(site)
            seen_in_batch.add(site_key)
            added_count += 1
    st.session_state.bulk_sites_input = "\n".join(duplicate_lines)
    st.session_state.bulk_site_result = (added_count, len(duplicate_lines), len(lines) > 0)


def delete_site(site_id: int):
    """حذف موقع بحث مستهدف عبر رقمه (id)"""
    cursor.execute("DELETE FROM search_sites WHERE id = %s", (site_id,))


def delete_news(news_id: int):
    """حذف خبر معين من جدول الأخبار عبر رقمه (id)"""
    cursor.execute("DELETE FROM news WHERE id = %s", (news_id,))


def delete_all_news():
    """حذف كل الأخبار المخزّنة دفعة واحدة"""
    cursor.execute("DELETE FROM news")


def toggle_site(site_id: int, new_state: int):
    """تفعيل / تعطيل موقع بحث مستهدف"""
    cursor.execute("UPDATE search_sites SET active = %s WHERE id = %s", (new_state, site_id))


def log_automation(action: str, status: str, details: str = ""):
    """تسجيل عملية أتمتة (نجاح أو فشل) في جدول automation_log"""
    cursor.execute(
        "INSERT INTO automation_log (action, status, details, timestamp) VALUES (%s, %s, %s, %s)",
        (action, status, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )


def send_to_n8n(webhook_url: str, payload: dict, timeout: int = 10):
    """
    إرسال بيانات إلى n8n عبر Webhook.
    يشترط أن يكون n8n شغّال (سواء على نفس اللابتوب أو أونلاين)
    وأن يكون الرابط الصحيح لعقدة Webhook Trigger داخل الـ workflow.

    timeout: مدة الانتظار بالثواني قبل ما نعتبر الطلب فاشل. القيمة الافتراضية
    (10 ثواني) مناسبة للعمليات السريعة، لكن الذكاء الاصطناعي قد يحتاج وقت
    أطول بكثير (خصوصاً وهو يقرأ كل الأخبار)، فلازم نمرر قيمة أعلى له تحديداً.
    """
    if not webhook_url:
        log_automation("إرسال إلى n8n", "فشل", "لا يوجد رابط Webhook محفوظ بصفحة الإعدادات")
        return False, "لا يوجد رابط Webhook محفوظ. روح صفحة ⚙️ الإعدادات وأدخل الرابط أولاً."
    try:
        response = requests.post(webhook_url, json=payload, timeout=timeout)
        if response.status_code in (200, 201):
            log_automation("إرسال إلى n8n", "نجاح", str(payload))
            return True, response.text
        else:
            log_automation("إرسال إلى n8n", "فشل", f"HTTP {response.status_code}")
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        log_automation("إرسال إلى n8n", "فشل", str(e))
        return False, str(e)


def extract_ai_answer(raw_text: str):
    """
    تستخرج نص الجواب من رد n8n مهما كان شكله:
    - كائن مباشر: {"answer": "..."}
    - قائمة فيها عنصر: [{"output": "..."}]
    - قائمة فيها أكثر من عنصر: ناخذ أول نص غير فاضي
    - نص JSON مشفّر مرتين: "{\"answer\": \"...\"}"
    - نص عادي بدون JSON إطلاقاً: نرجعه كما هو
    ترجع النص المستخرج، أو None لو ما لقت شي مفهوم.
    """
    possible_keys = ["answer", "output", "text", "response", "message", "result"]

    def dig(node, depth=0):
        if depth > 4:  # حماية من التكرار اللانهائي لو البيانات متداخلة بشكل غريب
            return None
        # لو نص، جرّب تفكّه كـ JSON (يعالج حالة التشفير المضاعف)
        if isinstance(node, str):
            stripped = node.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return dig(json.loads(stripped), depth + 1)
                except Exception:
                    return None
            return None
        # لو قائمة، دور بعناصرها لحد ما تلقى إجابة
        if isinstance(node, list):
            for item in node:
                found = dig(item, depth + 1)
                if found:
                    return found
            return None
        # لو كائن، دور بأسماء الحقول المعروفة أولاً
        if isinstance(node, dict):
            for key in possible_keys:
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            # لو ما لقى بالأسماء المعروفة، دور بأي قيمة نصية غير فاضية بالكائن
            for value in node.values():
                found = dig(value, depth + 1)
                if found:
                    return found
        return None

    try:
        parsed = json.loads(raw_text)
    except Exception:
        # الرد أصلاً مو JSON، يمكن نص عادي مباشر من n8n
        return raw_text.strip() if raw_text and raw_text.strip() else None

    return dig(parsed)


def extract_ai_file(raw_text: str):
    """
    تستخرج بيانات ملف مرفق (إن وجد) من رد n8n، عشان يقدر المساعد الذكي
    يرسل لك ملف فعلي (مثلاً تصدير الأخبار Excel) مو بس يقول "تم" بالنص.

    مهم جداً: هذي الدالة تقرأ فقط الملف اللي يرسله n8n بالرد — لازم تضيف
    بالـ workflow نفسه عقدة تنشئ الملف وترسله ضمن JSON برد الـ Webhook
    بأحد هالشكلين:
        {"file_base64": "<محتوى الملف مشفّر base64>", "file_name": "news.xlsx"}
    أو:
        {"file_url": "https://رابط-مباشر-للملف", "file_name": "news.xlsx"}
    بدون ما n8n يرسل هالحقول، ما فيه ملف يوصل هنا مهما كان رد النص.

    ترجع dict فيها name / base64 / url / mime، أو None لو ما فيه ملف بالرد.
    """
    try:
        parsed = json.loads(raw_text)
    except Exception:
        return None

    def dig(node, depth=0):
        if depth > 4:
            return None
        if isinstance(node, dict):
            if node.get("file_base64") or node.get("file_url"):
                return {
                    "name": node.get("file_name") or node.get("filename") or "file",
                    "base64": node.get("file_base64"),
                    "url": node.get("file_url"),
                    "mime": node.get("mime_type") or "application/octet-stream",
                }
            for value in node.values():
                found = dig(value, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = dig(item, depth + 1)
                if found:
                    return found
        return None

    return dig(parsed)


def render_assistant_file(file_info: dict, unique_key: str):
    """تعرض زر تحميل (أو رابط) للملف المرفق من رد المساعد الذكي، إن وُجد"""
    if not file_info:
        return
    if file_info.get("base64"):
        try:
            file_bytes = base64.b64decode(file_info["base64"])
            st.download_button(
                f"⬇️ تحميل {file_info['name']}",
                data=file_bytes,
                file_name=file_info["name"],
                mime=file_info.get("mime", "application/octet-stream"),
                key=unique_key,
            )
        except Exception:
            st.caption("⚠️ وصل ملف بالرد لكن تعذّر فك تشفيره.")
    elif file_info.get("url"):
        st.markdown(f"[⬇️ تحميل {file_info['name']}]({file_info['url']})")


@st.cache_data(ttl=5, show_spinner=False)
def get_cached_news_count(_conn):
    """
    عدد الأخبار، لكن مخزّن مؤقتاً لمدة 5 ثواني بدل ما نستعلم قاعدة البيانات
    بكل تنقل بين الصفحات. هذا يسرّع التنقل بشكل كبير، ولسا يبقى "شبه فوري"
    لأن أقصى تأخير ممكن هو 5 ثواني بس.
    """
    return int(pd.read_sql_query("SELECT COUNT(*) AS c FROM news", _conn)["c"].iloc[0])


@st.cache_data(ttl=5, show_spinner=False)
def get_cached_recent_failures(_conn):
    """
    نفس فكرة get_cached_news_count لكن لصندوق تنبيهات الفشل.

    تعديل مهم: بدل ما نجيب كل سجلات الفشل غير المُطّلع عليها (وهذا كان
    يخلي نفس الرابط، لو فشل عدة مرات متتالية، يطلع بعدة أسطر منفصلة
    ويتكدس التنبيه) — الحين نجيب سطر واحد بس لكل رابط (details): وهو
    آخر محاولة فشل له. لو نفس الرابط فشل مرة ثانية، السطر الجديد يحل
    محل القديم تلقائياً بالعرض، بدل ما يضاف كسطر إضافي. السجلات القديمة
    تبقى محفوظة بقاعدة البيانات لأغراض التاريخ (سجل الأتمتة الكامل)،
    وتُستبعد فقط من هذا الصندوق.
    """
    return pd.read_sql_query("""
        SELECT * FROM (
            SELECT DISTINCT ON (details) *
            FROM automation_log
            WHERE status = 'فشل' AND acknowledged = 0
            ORDER BY details, id DESC
        ) latest_per_link
        ORDER BY id DESC
        LIMIT 100
    """, _conn)


# ============================================================
# 4ب) إشعارات فورية على مستوى التطبيق كامل (تظهر بأي صفحة تكون فيها)
# ------------------------------------------------------------
# 1) إشعار عند وصول خبر جديد لجدول news.
# 2) إشعار فوري (توست) عند تسجيل أي عملية فاشلة بجدول automation_log،
#    بالإضافة لصندوق تنبيه دائم يعرض فقط الإخفاقات اللي ما تم الاطلاع عليها
#    (سطر واحد لكل رابط — آخر فشل له فقط، بدل تراكم كل المحاولات).
#
# ملاحظة مهمة: هذا القسم "قراءة فقط" من قاعدة البيانات لعرض تنبيه بالواجهة،
# ولا يوقف ولا يؤثر إطلاقاً على عمل الـ workflow بـ n8n — الـ workflow
# يكمل شغله بشكل مستقل تماماً سواء ظهر الإشعار أو لا.
#
# عشان تنبيه "رابط ما اشتغل" يظهر، لازم n8n (أو أي عقدة بالـ workflow
# تحاول تفتح رابط من جدول search_sites) تسجّل النتيجة بجدول automation_log
# بنفس طريقة log_automation أعلاه، مثلاً عبر عقدة Postgres تنفّذ:
#   INSERT INTO automation_log (action, status, details, timestamp)
#   VALUES ('زيارة رابط', 'فشل', '<رابط الموقع اللي فشل>', '<الوقت>')
#
# طريقة العمل: لما تضغط "تم الاطلاع"، كل محاولات الفشل غير المُطّلع
# عليها لنفس الروابط الظاهرة تُعلَّم acknowledged=1 فتختفي فوراً من صندوق
# التنبيه ولا ترجع تطلع لك مرة ثانية — لكنها تبقى محفوظة بقاعدة البيانات
# (ما تُحذف نهائياً) عشان تضل تظهر بسجل الأتمتة الكامل وبحساب "آخر حالة
# لكل رابط" بصفحة مواقع البحث المستهدفة.
# ============================================================

# --- إشعار: خبر جديد وصل (يظهر ويختفي تلقائياً بعد ثواني) ---
current_news_count = get_cached_news_count(conn)
if "last_seen_news_count" not in st.session_state:
    st.session_state.last_seen_news_count = current_news_count
elif current_news_count > st.session_state.last_seen_news_count:
    new_items = current_news_count - st.session_state.last_seen_news_count
    st.toast(f"🆕 وصل {new_items} خبر جديد!", icon="📰")
    st.session_state.last_seen_news_count = current_news_count

# --- تحميل الإخفاقات اللي لسا ما تم الاطلاع عليها (سطر واحد لكل رابط) ---
df_recent_failures = get_cached_recent_failures(conn)

# --- إشعار فوري (توست): فشل جديد وصل بالوقت الفعلي ---
current_failure_count = len(df_recent_failures)
if "last_seen_failure_count" not in st.session_state:
    st.session_state.last_seen_failure_count = current_failure_count
elif current_failure_count > st.session_state.last_seen_failure_count:
    new_failures = current_failure_count - st.session_state.last_seen_failure_count
    st.toast(f"⚠️ وصل {new_failures} فشل جديد!", icon="🚫")
    st.session_state.last_seen_failure_count = current_failure_count

# --- تنبيه دائم: يبقى ظاهر لين تعلّمه "تم الاطلاع"، وقتها يختفي نهائياً (ما يرجع يطلع) ---
if not df_recent_failures.empty:
    with st.container():
        st.error(f"⚠️ فيه {len(df_recent_failures)} رابط/عملية فشلت:")
        for _, frow in df_recent_failures.iterrows():
            st.write(f"❌ الرابط: **{frow['details']}** — بتاريخ {frow['timestamp']}")
        if st.button("✅ تم الاطلاع، إخفاء هذا التنبيه", key="ack_failures_btn"):
            # نجدد الاتصال أولاً (نفس أسلوب bulk_add_keywords_callback) قبل التحديث،
            # لأن هذا الزر قد يُضغط بعد ما يضل التطبيق مفتوح فترة طويلة بدون
            # استخدام، فيكون Supabase سكّر الاتصال القديم من فترة (Idle Timeout)
            conn = get_healthy_connection()
            cursor = conn.cursor()
            try:
                # نعلّم كل محاولات الفشل غير المُطّلع عليها لنفس الروابط
                # الظاهرة حالياً كـ "تم الاطلاع" (مو بس السطر الظاهر لكل
                # رابط)، حتى ما ترجع تطلع لك محاولة فشل قديمة نسيتها لاحقاً.
                # السجل يبقى محفوظاً بقاعدة البيانات (ما يُحذف نهائياً).
                failed_links = df_recent_failures["details"].tolist()
                for link in failed_links:
                    cursor.execute(
                        "UPDATE automation_log SET acknowledged = 1 "
                        "WHERE details = %s AND status = 'فشل' AND acknowledged = 0",
                        (link,)
                    )
                get_cached_recent_failures.clear()  # نفرّغ الكاش فوراً حتى يختفي التنبيه بدون انتظار
                st.session_state.last_seen_failure_count = 0
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ تعذّر تحديث التنبيهات فعلياً: {e}")
    st.divider()


# ============================================================
# 5) القائمة الجانبية (Sidebar Navigation)
# نحاول استخدام مكتبة streamlit-option-menu للحصول على تصميم
# احترافي بأيقونات، وإن لم تكن مثبّتة نرجع تلقائياً لقائمة عادية
# ============================================================
try:
    from streamlit_option_menu import option_menu
    with st.sidebar:
        page = option_menu(
            menu_title="🤖 الوكيل الذكي",
            options=[
                "لوحة المعلومات",
                "الكلمات المفتاحية",
                "مواقع البحث المستهدفة",
                "الأخبار والمساعد الذكي",
                "الأتمتة (n8n)",
                "قوقل شيت",
                "الإعدادات"
            ],
            icons=["speedometer2", "tags", "globe", "newspaper", "gear-wide-connected", "table", "sliders"],
            menu_icon="robot",
            default_index=0,
            styles={
                "container": {"background-color": "transparent"},
                "nav-link-selected": {"background-color": "#6366f1"},
            }
        )
except ModuleNotFoundError:
    st.sidebar.warning("لتفعيل القائمة العصرية بالأيقونات، نفّذ:\npip install streamlit-option-menu")
    page = st.sidebar.radio("القائمة الرئيسية:", [
        "لوحة المعلومات",
        "الكلمات المفتاحية",
        "مواقع البحث المستهدفة",
        "الأخبار والمساعد الذكي",
        "الأتمتة (n8n)",
        "قوقل شيت",
        "الإعدادات"
    ])


# ============================================================
# 6) لوحة المعلومات (Dashboard) — صفحة جديدة تلخّص كل شيء
# ============================================================
if page == "لوحة المعلومات":
    st.markdown("""
    <div class="main-title">
        <h1>🤖 لوحة تحكم الوكيل الذكي</h1>
        <p>نظرة عامة سريعة على حالة النظام والبيانات المخزّنة محلياً</p>
    </div>
    """, unsafe_allow_html=True)

    df_kw = pd.read_sql_query("SELECT * FROM keywords", conn)
    df_news = pd.read_sql_query("SELECT * FROM news", conn)
    df_log = pd.read_sql_query("SELECT * FROM automation_log ORDER BY id DESC LIMIT 5", conn)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔑 عدد الكلمات المفتاحية", len(df_kw))
    col2.metric("✅ الكلمات النشطة", int(df_kw["active"].sum()) if not df_kw.empty else 0)
    col3.metric("📰 عدد الأخبار المخزنة", len(df_news))
    col4.metric("⚙️ عمليات أتمتة مسجّلة", len(pd.read_sql_query("SELECT * FROM automation_log", conn)))

    st.divider()
    st.subheader("📋 آخر 5 عمليات أتمتة")
    if df_log.empty:
        st.info("لا توجد أي عمليات أتمتة مسجّلة بعد. جرّب صفحة (الأتمتة n8n).")
    else:
        st.dataframe(df_log, use_container_width=True, hide_index=True)


# ============================================================
# 7) صفحة إدارة الكلمات المفتاحية (مع حذف/تفعيل/تعطيل)
# ============================================================
elif page == "الكلمات المفتاحية":
    st.markdown('<div class="main-title"><h1>🔑 إدارة الكلمات المفتاحية</h1></div>', unsafe_allow_html=True)

    with st.form("add_kw_form", clear_on_submit=True):
        new_kw = st.text_input("أدخل كلمة مفتاحية جديدة:")
        submitted = st.form_submit_button("➕ إضافة الكلمة")
        if submitted and new_kw.strip():
            if keyword_exists(new_kw.strip()):
                st.warning("⚠️ هذه الكلمة مكررة، لم تتم إضافتها.")
            else:
                add_keyword(new_kw.strip())
                st.success("تمت الإضافة بنجاح!")
                st.rerun()

    # ---- إضافة عدة كلمات مفتاحية دفعة واحدة ----
    with st.expander("📋 إضافة عدة كلمات دفعة واحدة"):
        st.caption("الصق كل كلمة بسطر لحالها (سطر جديد لكل كلمة)")
        st.text_area("الكلمات (كلمة بكل سطر):", height=150, key="bulk_keywords_input")
        st.button("➕ إضافة كل الكلمات دفعة واحدة", on_click=bulk_add_keywords_callback)
        if st.session_state.get("bulk_kw_result") is not None:
            added, dup, had_input = st.session_state.bulk_kw_result
            if not had_input:
                st.warning("الصق كلمة واحدة على الأقل، كل كلمة بسطر.")
            else:
                if added:
                    st.success(f"تمت إضافة {added} كلمة بنجاح!")
                if dup:
                    st.warning(f"⚠️ {dup} كلمة مكررة لم تتم إضافتها، وبقيت في الصندوق أعلاه.")
            st.session_state.bulk_kw_result = None

    st.divider()
    df_kw = pd.read_sql_query("SELECT * FROM keywords", conn)

    if df_kw.empty:
        st.info("لا توجد كلمات مفتاحية بعد.")
    else:
        # مربع بحث لتصفية الجدول (ميزة إضافية)
        search = st.text_input("🔍 بحث داخل الكلمات:")
        if search:
            df_kw = df_kw[df_kw["keyword"].str.contains(search, case=False, na=False)]

        # ---- حذف متعدد: حدد أكثر من كلمة ثم احذفهم دفعة واحدة ----
        if st.button("🗑️ حذف الكلمات المحددة", key="bulk_delete_kw_btn"):
            selected_ids = [
                row["id"] for _, row in df_kw.iterrows()
                if st.session_state.get(f"sel_kw_{row['id']}", False)
            ]
            if selected_ids:
                for kw_id in selected_ids:
                    delete_keyword(kw_id)
                st.success(f"تم حذف {len(selected_ids)} كلمة محددة بنجاح!")
                st.rerun()
            else:
                st.warning("لم تحدد أي كلمة للحذف بعد (فعّل مربع التحديد بجانب كل كلمة أولاً).")

        for _, row in df_kw.iterrows():
            c0, c1, c2, c3 = st.columns([1, 4, 3, 2])
            c0.checkbox("تحديد", value=False, key=f"sel_kw_{row['id']}", label_visibility="collapsed")
            c1.write(f"**{row['keyword']}**")
            new_state = c2.toggle("مفعّلة", value=bool(row["active"]), key=f"toggle_{row['id']}")
            if new_state != bool(row["active"]):
                toggle_keyword(row["id"], int(new_state))
                st.rerun()
            if c3.button("🗑️ حذف", key=f"del_{row['id']}"):
                delete_keyword(row["id"])
                st.rerun()


# ============================================================
# 7ب) صفحة إدارة مواقع البحث المستهدفة (نفس أسلوب الكلمات المفتاحية)
# n8n يقدر يقرأ من جدول search_sites مباشرة عبر عقدة Postgres
# ============================================================
elif page == "مواقع البحث المستهدفة":
    st.markdown('<div class="main-title"><h1>🌐 مواقع البحث المستهدفة</h1></div>', unsafe_allow_html=True)
    st.caption("أضف هنا المواقع اللي تبي n8n يدور فيها عن الكلمات المفتاحية (مثلاً: site1.com، site2.com)")

    with st.form("add_site_form", clear_on_submit=True):
        new_site = st.text_input("أدخل رابط أو اسم موقع جديد:")
        submitted = st.form_submit_button("➕ إضافة الموقع")
        if submitted and new_site.strip():
            if site_exists(new_site.strip()):
                st.warning("⚠️ هذا الموقع مكرر، لم تتم إضافته.")
            else:
                add_site(new_site.strip())
                st.success("تمت الإضافة بنجاح!")
                st.rerun()

    # ---- إضافة عدة مواقع دفعة واحدة ----
    with st.expander("📋 إضافة عدة مواقع دفعة واحدة"):
        st.caption("الصق كل رابط بسطر لحاله (سطر جديد لكل موقع)")
        st.text_area("الروابط (رابط بكل سطر):", height=150, key="bulk_sites_input")
        st.button("➕ إضافة كل المواقع دفعة واحدة", on_click=bulk_add_sites_callback)
        if st.session_state.get("bulk_site_result") is not None:
            added, dup, had_input = st.session_state.bulk_site_result
            if not had_input:
                st.warning("الصق رابط واحد على الأقل، كل رابط بسطر.")
            else:
                if added:
                    st.success(f"تمت إضافة {added} موقع بنجاح!")
                if dup:
                    st.warning(f"⚠️ {dup} موقع مكرر لم تتم إضافته، وبقي في الصندوق أعلاه.")
            st.session_state.bulk_site_result = None

    st.divider()
    df_sites = pd.read_sql_query("SELECT * FROM search_sites", conn)

    if df_sites.empty:
        st.info("لا توجد مواقع مضافة بعد.")
    else:
        search = st.text_input("🔍 بحث داخل المواقع:")
        if search:
            df_sites = df_sites[df_sites["site_url"].str.contains(search, case=False, na=False)]

        # ---- حذف متعدد: حدد أكثر من موقع ثم احذفهم دفعة واحدة ----
        if st.button("🗑️ حذف المواقع المحددة", key="bulk_delete_site_btn"):
            selected_ids = [
                row["id"] for _, row in df_sites.iterrows()
                if st.session_state.get(f"sel_site_{row['id']}", False)
            ]
            if selected_ids:
                for site_id in selected_ids:
                    delete_site(site_id)
                st.success(f"تم حذف {len(selected_ids)} موقع محدد بنجاح!")
                st.rerun()
            else:
                st.warning("لم تحدد أي موقع للحذف بعد (فعّل مربع التحديد بجانب كل موقع أولاً).")

        # ---- حالة كل رابط (يشتغل / ما يشتغل) ----
        # نجيب آخر عملية تسجّلت بجدول automation_log لكل رابط (action = 'زيارة رابط')
        # سواء كانت نجاح أو فشل، ونعرضها بشكل دائم بجانب كل موقع بالأسفل،
        # مو مجرد إشعار عابر يختفي. لازم n8n يسجّل بهذا الشكل حتى تظهر الحالة:
        #   INSERT INTO automation_log (action, status, details, timestamp)
        #   VALUES ('زيارة رابط', 'نجاح' أو 'فشل', '<رابط الموقع>', '<الوقت>')
        df_link_checks = pd.read_sql_query(
            "SELECT details, status, timestamp FROM automation_log "
            "WHERE action = 'زيارة رابط' ORDER BY id DESC", conn
        )
        latest_status_by_link = {}
        for _, log_row in df_link_checks.iterrows():
            link = log_row["details"]
            if link not in latest_status_by_link:
                latest_status_by_link[link] = (log_row["status"], log_row["timestamp"])

        for _, row in df_sites.iterrows():
            c0, c1, c2, c3, c4 = st.columns([1, 3, 2, 2, 1.5])
            c0.checkbox("تحديد", value=False, key=f"sel_site_{row['id']}", label_visibility="collapsed")
            c1.write(f"**{row['site_url']}**")
            new_state = c2.toggle("مفعّل", value=bool(row["active"]), key=f"site_toggle_{row['id']}")
            if new_state != bool(row["active"]):
                toggle_site(row["id"], int(new_state))
                st.rerun()

            status_info = latest_status_by_link.get(row["site_url"])
            if status_info is None:
                c3.caption("⏳ لم يتم فحصه بعد")
            elif status_info[0] == "نجاح":
                c3.success(f"✅ يشتغل ({status_info[1]})")
            else:
                c3.error(f"❌ ما يشتغل ({status_info[1]})")

            if c4.button("🗑️ حذف", key=f"site_del_{row['id']}"):
                delete_site(row["id"])
                st.rerun()

    # ---- مربع دائم: كل الروابط اللي ما اشتغلت، مع تاريخ كل فشل ----
    st.divider()
    st.subheader("🔴 الروابط اللي ما اشتغلت")
    df_failed_links = pd.read_sql_query(
        "SELECT details AS الرابط, timestamp AS التاريخ FROM automation_log "
        "WHERE action = 'زيارة رابط' AND status = 'فشل' ORDER BY id DESC",
        conn
    )
    if df_failed_links.empty:
        st.info("لا يوجد أي رابط فشل حتى الآن.")
    else:
        st.dataframe(df_failed_links, use_container_width=True, hide_index=True)


# ============================================================
# 8) صفحة الأخبار والمساعد الذكي
# ============================================================
elif page == "الأخبار والمساعد الذكي":
    st.markdown('<div class="main-title"><h1>📰 الأخبار المسحوبة ومساعد الذكاء الاصطناعي</h1></div>', unsafe_allow_html=True)

    # ملاحظة: التحديث التلقائي (auto-refresh) اتشال من هذي الصفحة بالكامل —
    # كان يقاطع انتظار رد الذكاء الاصطناعي ويلغيه قبل ما يظهر (خصوصاً بأول
    # سؤال بأي محادثة)، لأنه يتفعّل بغض النظر عن وجود طلب قيد الانتظار.
    # لو تبي إشعار بالأخبار الجديدة، استخدم زر "تحديث" يدوي بدل التلقائي.

    if st.button("🔄 تحديث الأخبار الآن"):
        st.rerun()

    # الترتيب حسب id تنازلياً (وليس حسب عمود date النصي) لأن id يعكس فعلياً
    # ترتيب وصول الخبر لقاعدة البيانات، بغض النظر عن شكل نص التاريخ المرسل
    df_news = pd.read_sql_query("SELECT * FROM news ORDER BY id DESC", conn)

    if df_news.empty:
        st.info("لا توجد أخبار مخزّنة بعد. يمكن لـ n8n تعبئة هذا الجدول تلقائياً (راجع صفحة الأتمتة).")
    else:
        sites = ["الكل"] + sorted(df_news["site"].dropna().unique().tolist())
        chosen_site = st.selectbox("تصفية حسب الموقع:", sites)
        if chosen_site != "الكل":
            df_news = df_news[df_news["site"] == chosen_site]

        # column_config يجبر عمود date يظهر كنص كامل (تاريخ + وقت) بدل ما
        # يكتشفه Streamlit تلقائياً كعمود تاريخ ويقص الوقت ويعرض اليوم فقط
        st.dataframe(
            df_news,
            use_container_width=True,
            hide_index=True,
            column_config={"date": st.column_config.TextColumn("التاريخ")}
        )

        # ترميز utf-8-sig يضيف "علامة ترميز" (BOM) في بداية الملف، وهذا
        # يخلي إكسل يتعرف على النص العربي صح بدل ما يطلعه رموز غريبة
        csv = df_news.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ تصدير البيانات (CSV / Excel)", data=csv, file_name="news.csv", mime="text/csv")

        # ---- حذف خبر معين لا تبيه ----
        with st.expander("🗑️ حذف خبر معين"):
            news_options = {
                f"#{row['id']} — {row['title'][:60]}": row['id']
                for _, row in df_news.iterrows()
            }
            selected_label = st.selectbox("اختر الخبر اللي تبي تحذفه:", list(news_options.keys()))
            if st.button("🗑️ تأكيد الحذف"):
                delete_news(news_options[selected_label])
                get_cached_news_count.clear()
                st.success("تم حذف الخبر بنجاح!")
                st.rerun()

        # ---- حذف عدة أخبار محددة أو كل الأخبار دفعة واحدة ----
        with st.expander("🗑️ حذف عدة أخبار أو كل الأخبار"):
            col_all, col_sel = st.columns(2)

            with col_all:
                st.caption("يمسح كل الأخبار الموجودة بالجدول نهائياً")
                confirm_all = st.checkbox("أوافق على حذف كل الأخبار", key="confirm_delete_all_news")
                if st.button("🗑️ حذف كل الأخبار المخزّنة", key="delete_all_news_btn", disabled=not confirm_all):
                    delete_all_news()
                    get_cached_news_count.clear()
                    st.success("تم حذف كل الأخبار بنجاح!")
                    st.rerun()

            with col_sel:
                st.caption("حدد الأخبار اللي تبي تحذفها من الجدول أدناه")
                for _, row in df_news.iterrows():
                    st.checkbox(
                        f"#{row['id']} — {row['title'][:60]}",
                        value=False,
                        key=f"sel_news_{row['id']}"
                    )
                if st.button("🗑️ حذف الأخبار المحددة", key="bulk_delete_news_btn"):
                    selected_news_ids = [
                        row["id"] for _, row in df_news.iterrows()
                        if st.session_state.get(f"sel_news_{row['id']}", False)
                    ]
                    if selected_news_ids:
                        for news_id in selected_news_ids:
                            delete_news(news_id)
                        get_cached_news_count.clear()
                        st.success(f"تم حذف {len(selected_news_ids)} خبر محدد بنجاح!")
                        st.rerun()
                    else:
                        st.warning("لم تحدد أي خبر للحذف بعد.")

    # ============================================================
    # 🤖 المساعد الذكي — مرتبط بـ n8n، ويجاوب فقط من الأخبار المخزّنة
    # ------------------------------------------------------------
    # طريقة العمل:
    # 1) أول رسالة بالمحادثة: نرسل معها كل الأخبار الموجودة بالجدول
    #    (بدون أي حد أقصى) + السؤال + معرّف جلسة (session_id) فريد.
    # 2) الرسائل اللي بعدها: نرسل فقط السؤال + نفس الـ session_id،
    #    بدون إعادة إرسال الأخبار، لأن n8n يحتفظ بها بذاكرة المحادثة
    #    (AI Memory) المربوطة بنفس الـ session_id، فتصير المحادثة
    #    سلسة ومتواصلة بدون تكرار إرسال كل الأخبار كل مرة.
    # 3) زر "محادثة جديدة" يصفّر كل شيء ويولّد session_id جديد،
    #    وبالتالي أول رسالة بالمحادثة الجديدة بترسل كل الأخبار من جديد.
    # 4) لو رد n8n فيه ملف مرفق (file_base64 أو file_url) يظهر زر تحميل
    #    فعلي تحت رسالة المساعد — راجع تعليق extract_ai_file بالأعلى
    #    لشكل الحقول المطلوبة من n8n حتى يوصلك الملف فعلياً.
    #
    # ملاحظة: رابط الـ Webhook هنا ما عاد حقل نص يعدّله أي زائر — يُقرأ
    # مباشرة من صفحة "⚙️ الإعدادات" (محفوظ بقاعدة البيانات).
    # ============================================================
    st.divider()
    st.subheader("🤖 المساعد الذكي (يجيب من الأخبار المخزّنة فقط عبر n8n)")

    ai_webhook_url = get_setting("ai_assistant_webhook")
    if not ai_webhook_url:
        st.warning("⚠️ ما فيه رابط Webhook محفوظ للمساعد الذكي بعد. روح صفحة ⚙️ الإعدادات وأدخله أولاً.")

    # تهيئة حالة الجلسة أول مرة فقط
    if "assistant_history" not in st.session_state:
        st.session_state.assistant_history = []
    if "assistant_session_id" not in st.session_state:
        st.session_state.assistant_session_id = str(uuid.uuid4())

    col_reset, _ = st.columns([1, 4])
    if col_reset.button("🗑️ محادثة جديدة"):
        st.session_state.assistant_history = []
        st.session_state.assistant_session_id = str(uuid.uuid4())
        st.rerun()

    # عرض المحادثة السابقة (مع أي ملف مرفق بكل رسالة، إن وُجد)
    for idx, msg in enumerate(st.session_state.assistant_history):
        st.chat_message(msg["role"]).write(msg["content"])
        if msg.get("file"):
            render_assistant_file(msg["file"], unique_key=f"hist_file_{idx}")

    user_query = st.chat_input("اسأل المساعد الذكي عن الأخبار...")
    if user_query:
        st.session_state.assistant_history.append({"role": "user", "content": user_query, "file": None})
        st.chat_message("user").write(user_query)

        # ما نرسل الأخبار كنص هنا؛ الذكاء الاصطناعي يستعلم عن قاعدة البيانات
        # مباشرة بنفسه من طرف n8n (عبر أداة Postgres)، فتكون إجاباته
        # (زي عدد الأخبار) دقيقة دايماً بدل ما يحاول يعدّها من نص طويل
        payload = {
            "query": user_query,
            "session_id": st.session_state.assistant_session_id,
        }

        # مهلة أطول (180 ثانية) لأن كل رسالة ترسل كل الأخبار كسياق للذكاء
        # الاصطناعي، وهذا يخلي وقت التفكير أطول من المعتاد
        with st.spinner("جاري التفكير..."):
            success, message = send_to_n8n(ai_webhook_url, payload, timeout=180)

        file_info = None
        if success:
            answer = extract_ai_answer(message)
            file_info = extract_ai_file(message)
            if not answer:
                answer = "لم يصل رد واضح من المساعد الذكي، حاول مرة أخرى."
        else:
            answer = f"تعذّر الوصول إلى المساعد الذكي حالياً: {message}"

        st.session_state.assistant_history.append({"role": "assistant", "content": answer, "file": file_info})
        st.chat_message("assistant").write(answer)
        if file_info:
            render_assistant_file(file_info, unique_key=f"new_file_{len(st.session_state.assistant_history)}")
        elif success and ("csv" in user_query.lower() or "اكسل" in user_query or "إكسل" in user_query or "ملف" in user_query):
            # تلميح: المستخدم يبدو يطلب ملف، لكن n8n ما أرجع أي ملف بالرد
            st.caption(
                "ℹ️ يبدو إنك طلبت ملف، لكن رد n8n ما فيه ملف مرفق فعلياً — "
                "تأكد إن الـ workflow يرجّع الملف ضمن الحقول file_base64/file_url."
            )


# ============================================================
# 9) صفحة الأتمتة (n8n) — سجل عمليات الأتمتة فقط
# ============================================================
elif page == "الأتمتة (n8n)":
    st.markdown('<div class="main-title"><h1>⚙️ الأتمتة عبر n8n</h1></div>', unsafe_allow_html=True)

    st.subheader("📋 سجل عمليات الأتمتة")
    df_log = pd.read_sql_query("SELECT * FROM automation_log ORDER BY id DESC", conn)
    if df_log.empty:
        st.info("لا توجد عمليات مسجّلة بعد.")
    else:
        st.dataframe(df_log, use_container_width=True, hide_index=True)


# ============================================================
# 9ب) صفحة قوقل شيت — عرض وتعديل شيت خارجي مباشرة داخل التطبيق
# ------------------------------------------------------------
# الجدول القابل للتعديل (st.data_editor) يعرض بيانات الشيت مباشرة، وتقدر
# منه: تعدّل أي خلية، تضيف صف جديد (من الصف الفاضي بالأسفل)، أو تحذف صف
# (تحدده وتضغط علامة الحذف اللي تطلع بجانبه). التعديلات تبقى محلية بالمتصفح
# لين تضغط زر "حفظ" — وقتها فقط تُرسل فعلياً وتُكتب على الشيت الحقيقي
# بقوقل (نفس فكرة ما يصير أي تغيير فعلي على الشيت الأصلي إلا بعد تأكيدك).
# ============================================================
elif page == "قوقل شيت":
    st.markdown('<div class="main-title"><h1>📊 قوقل شيت</h1></div>', unsafe_allow_html=True)
    st.caption("عدّل هنا مباشرة (إضافة صف / حذف صف / تغيير أي خلية)، ثم اضغط حفظ لإرسال التعديلات فعلياً إلى الشيت.")

    worksheet, error = get_worksheet()

    if error:
        st.warning(f"⚠️ {error}")
        st.info(
            "خطوات التفعيل (مرة وحدة بس):\n\n"
            "1) أنشئ Service Account من Google Cloud Console وفعّل عليه "
            "Google Sheets API + Google Drive API.\n"
            "2) نزّل مفتاح JSON للحساب، وحط مساره بمتغير GOOGLE_SERVICE_ACCOUNT_FILE "
            "بملف .env (أو حط محتوى الملف كامل كنص بمتغير GOOGLE_SERVICE_ACCOUNT_JSON).\n"
            "3) افتح الشيت بقوقل واعمل مشاركة (Share) مع بريد الـ Service Account "
            "(ينتهي بـ ...gserviceaccount.com) كصلاحية Editor.\n"
            "4) روح صفحة ⚙️ الإعدادات وألصق رابط الشيت أو معرّفه هناك واحفظ."
        )
    else:
        try:
            df_sheet = get_as_dataframe(worksheet, evaluate_formulas=True, dtype=str).dropna(how="all")
            df_sheet = df_sheet.fillna("")
        except Exception as e:
            st.error(f"⚠️ تعذّر قراءة بيانات الشيت: {e}")
            df_sheet = pd.DataFrame()

        # مفتاح متغيّر لصندوق التعديل: نزيده بعد كل حفظ/تحديث حتى يجبر
        # st.data_editor يعيد تحميل البيانات من جديد بدل ما يحتفظ بالتعديلات القديمة بالذاكرة
        if "gsheet_editor_key" not in st.session_state:
            st.session_state.gsheet_editor_key = 0

        edited_df = st.data_editor(
            df_sheet,
            use_container_width=True,
            num_rows="dynamic",  # يسمح بإضافة صفوف جديدة (بالصف الفاضي بالأسفل) أو حذف صفوف موجودة
            key=f"gsheet_editor_{st.session_state.gsheet_editor_key}",
        )

        col_save, col_reload = st.columns([1, 1])
        if col_save.button("💾 حفظ التعديلات على الشيت"):
            try:
                worksheet.clear()
                set_with_dataframe(worksheet, edited_df)
                st.success("تم حفظ كل التعديلات (إضافة/تعديل/حذف) على الشيت الفعلي بنجاح ✅")
                st.session_state.gsheet_editor_key += 1
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ تعذّر حفظ التعديلات على الشيت: {e}")

        if col_reload.button("🔄 تحديث من الشيت (تجاهل تعديلاتي غير المحفوظة)"):
            st.session_state.gsheet_editor_key += 1
            st.rerun()


# ============================================================
# 10) صفحة الإعدادات (مكان مركزي لرابط n8n ورابط شيت قوقل)
# ------------------------------------------------------------
# هنا فقط تُدخل/تعدّل رابط الـ Webhook اللي يحتاجه المساعد الذكي، بالإضافة
# لرابط/معرّف شيت قوقل اللي تبي تربطه بصفحة "قوقل شيت". القيم تُحفظ بجدول
# app_settings بقاعدة بيانات Supabase، يعني ما تروح لو أعدت نشر التطبيق
# أو غيّرت مكان استضافته — تبقى محفوظة دايماً.
# ============================================================
elif page == "الإعدادات":
    st.markdown('<div class="main-title"><h1>⚙️ الإعدادات</h1></div>', unsafe_allow_html=True)
    st.caption("عدّل الروابط هنا مرة وحدة، وباقي الصفحات بتقرأها تلقائياً من هنا.")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    with st.form("settings_form"):
        st.subheader("🤖 رابط Webhook — المساعد الذكي")
        ai_url = st.text_input(
            "رابط المساعد الذكي:",
            value=get_setting("ai_assistant_webhook"),
            placeholder="https://your-n8n-instance.app/webhook/ai-assistant"
        )

        st.subheader("📊 شيت قوقل")
        sheet_url = st.text_input(
            "رابط أو معرّف شيت قوقل:",
            value=get_setting("google_sheet_id"),
            placeholder="https://docs.google.com/spreadsheets/d/xxxxxxxx/edit"
        )
        st.caption("لصق الرابط الكامل من المتصفح كافي — التطبيق يستخرج المعرّف تلقائياً.")

        saved = st.form_submit_button("💾 حفظ الإعدادات")
        if saved:
            set_setting("ai_assistant_webhook", ai_url.strip())
            set_setting("google_sheet_id", sheet_url.strip())
            st.success("تم حفظ الإعدادات بنجاح ✅")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.info(
        "💡 ملاحظة: هذي الروابط محفوظة بقاعدة البيانات نفسها (Supabase)، مو بملف "
        "محلي على أي جهاز — يعني تقدر تعدّلها من أي مكان، وتبقى شغّالة حتى لو "
        "أعدت نشر التطبيق أو انتقلت لخطة أخرى."
    )
