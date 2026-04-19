#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات اسکرپر تلگرام با مدیریت از طریق پیام‌رسان بله
تمامی کد در یک فایل واحد
"""

import os
import sys
import json
import re
import hashlib
import time
import threading
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ========== تنظیمات اولیه ==========
DATA_FILE = "data.json"          # فایل یکپارچه داده‌ها
BALE_TOKEN = "868404371:IlfrvF53GWq6JattUbUCxHouhJpdgxWof-s"   # توکن ربات بله (در تولید از env استفاده کنید)

# الگوهای تشخیص کانفیگ (قابل گسترش)
PATTERNS = {
    "vmess": r"vmess://[A-Za-z0-9+/=]+",
    "vless": r"vless://[A-Za-z0-9+/=]+@[^\s]+",
    "trojan": r"trojan://[A-Za-z0-9@.]+",
    "ss": r"ss://[A-Za-z0-9@.]+",
    "hysteria2": r"hysteria2://[A-Za-z0-9@.]+",
    "tuic": r"tuic://[A-Za-z0-9@.]+"
}

# ========== توابع مدیریت داده ==========
def load_data():
    """بارگذاری تمام داده‌ها از فایل JSON یکپارچه"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # ساختار پیش‌فرض
    return {
        "channels": {
            "list": [],               # لیست نام کاربری کانال‌ها
            "auto_add_pending": {}    # کانال‌های در حال بررسی: {username: first_seen_time}
        },
        "database": {
            "configs": [],            # لیست کانفیگ‌ها با فیلدهای raw, type, hash, channel, timestamp
            "last_seen": {}           # آخرین زمان اسکرپ هر کانال
        },
        "status": {
            "active": True            # وضعیت فعال/غیرفعال ربات
        },
        "stats": {
            "total_configs": 0,       # تعداد کل کانفیگ‌های غیرتکراری
            "last_update": None       # زمان آخرین به‌روزرسانی
        }
    }

def save_data(data):
    """ذخیره داده‌ها در فایل JSON یکپارچه"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ========== توابع اسکرپ و استخراج ==========
def get_post_texts(channel_username, limit=10):
    """دریافت متن آخرین پست‌های عمومی کانال از t.me/s/"""
    url = f"https://t.me/s/{channel_username}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        texts = [msg.get_text(strip=True) for msg in messages[:limit]]
        return texts
    except Exception as e:
        print(f"⚠️ خطا در دریافت {channel_username}: {e}")
        return []

def extract_configs_from_text(text):
    """استخراج کانفیگ‌ها از متن با استفاده از regex"""
    configs = []
    for proto, pattern in PATTERNS.items():
        matches = re.findall(pattern, text)
        for m in matches:
            configs.append({
                "raw": m,
                "type": proto,
                "hash": hashlib.md5(m.encode()).hexdigest()
            })
    return configs

def update_database(channel, new_configs, data):
    """اضافه کردن کانفیگ‌های جدید به دیتابیس (غیرتکراری)"""
    db_configs = data["database"]["configs"]
    added = 0
    for cfg in new_configs:
        # بررسی تکراری
        duplicate = any(ex["hash"] == cfg["hash"] for ex in db_configs)
        if not duplicate:
            cfg["channel"] = channel
            cfg["timestamp"] = time.time()
            db_configs.append(cfg)
            added += 1
    data["database"]["last_seen"][channel] = time.time()
    # بروزرسانی آمار
    unique_hashes = set(c["hash"] for c in db_configs)
    data["stats"]["total_configs"] = len(unique_hashes)
    return added

def generate_subscription_link(data):
    """
    تولید لینک ساب (فایل subscription.txt) با قوانین:
    - اگر ربات غیرفعال است: یک کانفیگ دمو بدهد.
    - در غیر این صورت: ۵۰ کانفیگ غیرتکراری آخر (اولویت با جدیدترین‌ها)
    - اضافه کردن واترمارک با فرمت: Apr:19-[2:51PM]-(number:1)
    """
    if not data["status"]["active"]:
        demo = "vmess://eyJhZGQiOiJEZW1vIiwicG9ydCI6IjQ0MyIsInR5cGUiOiJub25lIn0="
        with open("subscription.txt", "w", encoding="utf-8") as f:
            f.write("# ربات موقتاً غیر فعال شده است. لطفاً صبر کنید.\n")
            f.write(demo)
        return

    all_configs = data["database"]["configs"]
    # مرتب‌سازی بر اساس جدیدترین
    all_configs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    # حذف تکراری بر اساس هش (حفظ اولین رخداد که جدیدترین است)
    unique = []
    seen = set()
    for cfg in all_configs:
        if cfg["hash"] not in seen:
            seen.add(cfg["hash"])
            unique.append(cfg)
    # ۵۰ تای اول
    final = unique[:50]

    # واترمارک
    now = datetime.now()
    month_map = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                 7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    month_abbr = month_map[now.month]
    day = now.day
    hour12 = now.strftime("%I:%M%p").lstrip("0")
    watermark_template = f"{month_abbr}:{day}-[{hour12}]-(number:{{}})"
    
    lines = []
    for idx, cfg in enumerate(final, start=1):
        lines.append(f"# {watermark_template.format(idx)}")
        lines.append(cfg["raw"])
    
    with open("subscription.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    data["stats"]["last_update"] = time.time()
    save_data(data)

def auto_add_channels(data):
    """
    بررسی کانال‌های در انتظار (auto_add_pending):
    - اگر ۳ ساعت از اولین مشاهده گذشته باشد، یکبار اسکرپ می‌شود.
    - اگر حداقل یک کانفیگ معتبر داشته باشد، به لیست اصلی اضافه می‌شود.
    """
    pending = data["channels"].get("auto_add_pending", {})
    now_ts = time.time()
    to_add = []
    for cand, first_seen in list(pending.items()):
        if now_ts - first_seen > 10800:  # 3 ساعت
            texts = get_post_texts(cand, limit=5)
            has_config = False
            for text in texts:
                if extract_configs_from_text(text):
                    has_config = True
                    break
            if has_config:
                to_add.append(cand)
            # حذف از pending چه اضافه شود چه نشود
            del pending[cand]
    for cand in to_add:
        if cand not in data["channels"]["list"]:
            data["channels"]["list"].append(cand)
            print(f"✅ کانال جدید به صورت خودکار اضافه شد: {cand}")
    if to_add:
        data["channels"]["auto_add_pending"] = pending
        save_data(data)

def scrape_all_channels():
    """اسکرپ تمام کانال‌های فعال و به‌روزرسانی دیتابیس و لینک ساب"""
    print("🔄 شروع اسکرپ کانال‌ها...")
    data = load_data()
    channel_list = data["channels"]["list"]
    
    for ch in channel_list:
        print(f"🔍 اسکرپ کانال: {ch}")
        texts = get_post_texts(ch, limit=10)
        all_new_configs = []
        for text in texts:
            configs = extract_configs_from_text(text)
            all_new_configs.extend(configs)
        added = update_database(ch, all_new_configs, data)
        print(f"   ➕ {added} کانفیگ جدید اضافه شد")
        
        # استخراج لینک کانال‌های دیگر از متن برای auto-add
        for text in texts:
            found = re.findall(r"t\.me/([a-zA-Z][a-zA-Z0-9_]{4,})", text)
            for new_ch in found:
                if new_ch not in channel_list and new_ch not in data["channels"].get("auto_add_pending", {}):
                    data["channels"].setdefault("auto_add_pending", {})[new_ch] = time.time()
                    save_data(data)
    
    # اضافه شدن خودکار کانال‌های معتبر
    auto_add_channels(data)
    # بازخوانی دیتا بعد از تغییرات
    data = load_data()
    generate_subscription_link(data)
    save_data(data)
    print("✅ اسکرپ کامل شد. لینک ساب به‌روزرسانی گردید.")

# ========== توابع ربات بله (مدیریت با دکمه) ==========
def bale_send_message(chat_id, text, keyboard=None):
    """ارسال پیام به ربات بله"""
    url = f"https://api.bale.ai/v1/bot{BALE_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال پیام به بله: {e}")

def bale_get_updates(offset=None):
    """دریافت آپدیت‌ها از ربات بله"""
    url = f"https://api.bale.ai/v1/bot{BALE_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        return resp.json().get("result", [])
    except:
        return []

# صفحه کلیدهای شیشه‌ای
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📡 دریافت لینک ساب", "callback_data": "get_sub"}],
            [{"text": "➕ مدیریت کانال‌ها", "callback_data": "manage_channels"}],
            [{"text": "⏸️ توقف/راه‌اندازی", "callback_data": "toggle_status"}]
        ]
    }

def manage_channels_keyboard(data):
    """ساخت دکمه‌های مدیریت کانال با لیست فعلی"""
    channels = data["channels"]["list"]
    buttons = []
    for ch in channels:
        buttons.append([{"text": f"❌ حذف {ch}", "callback_data": f"remove_ch:{ch}"}])
    buttons.append([{"text": "➕ افزودن کانال جدید", "callback_data": "add_ch"}])
    buttons.append([{"text": "🔙 بازگشت", "callback_data": "main_menu"}])
    return {"inline_keyboard": buttons}

def handle_callback(chat_id, callback_data):
    """مدیریت کلیک روی دکمه‌ها"""
    data = load_data()
    
    if callback_data == "get_sub":
        # لینک ساب (آدرس raw فایل در گیت‌هاب - باید تنظیم شود)
        # در اینجا فرض می‌کنیم فایل در سرور فعلی قابل دسترسی است
        sub_url = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/subscription.txt"
        bale_send_message(chat_id, f"🔗 لینک ساب شما:\n{sub_url}\n\nکافی است در اپلیکیشن خود وارد کنید.")
    
    elif callback_data == "manage_channels":
        kb = manage_channels_keyboard(data)
        bale_send_message(chat_id, "📋 لیست کانال‌های تحت نظارت:", keyboard=kb)
    
    elif callback_data == "toggle_status":
        new_status = not data["status"]["active"]
        data["status"]["active"] = new_status
        save_data(data)
        state = "فعال" if new_status else "غیرفعال"
        bale_send_message(chat_id, f"⚙️ وضعیت ربات به {state} تغییر کرد.")
        # بلافاصله لینک ساب را بازنویسی کن
        generate_subscription_link(data)
    
    elif callback_data == "add_ch":
        bale_send_message(chat_id, "لطفاً نام کاربری کانال را بدون @ ارسال کنید:")
        # برای سادگی، در اینجا از حافظه موقت استفاده نمی‌کنیم، بلکه منتظر پیام بعدی می‌مانیم
        # در یک ربات حرفه‌ای باید از FSM استفاده کرد. اما برای نمونه، فرض می‌کنیم کاربر بلافاصله نام کانال را می‌فرستد.
        # ما در تابع handle_message وضعیت را بررسی می‌کنیم: اگر کاربر در حالت افزودن باشد.
        # برای سادگی، یک متغیر سراسری ساده (اما ناامن) تعریف می‌کنیم:
        global waiting_for_channel
        waiting_for_channel[chat_id] = True
    
    elif callback_data.startswith("remove_ch:"):
        ch = callback_data.split(":", 1)[1]
        if ch in data["channels"]["list"]:
            data["channels"]["list"].remove(ch)
            save_data(data)
            bale_send_message(chat_id, f"✅ کانال {ch} از لیست حذف شد.")
            # نمایش مجدد منوی مدیریت
            kb = manage_channels_keyboard(data)
            bale_send_message(chat_id, "لیست به‌روز شد:", keyboard=kb)
        else:
            bale_send_message(chat_id, "کانال مورد نظر یافت نشد.")
    
    elif callback_data == "main_menu":
        bale_send_message(chat_id, "🏠 منوی اصلی:", keyboard=main_menu_keyboard())

def handle_message(chat_id, text):
    """مدیریت پیام‌های متنی (برای افزودن کانال)"""
    global waiting_for_channel
    if waiting_for_channel.get(chat_id):
        # پاک کردن حالت انتظار
        waiting_for_channel[chat_id] = False
        # اعتبارسنجی نام کاربری
        username = text.strip().lstrip('@')
        if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{4,}$", username):
            data = load_data()
            if username not in data["channels"]["list"]:
                data["channels"]["list"].append(username)
                save_data(data)
                bale_send_message(chat_id, f"✅ کانال {username} با موفقیت اضافه شد.")
                # یکبار اسکرپ سریع برای گرفتن کانفیگ‌های اولیه؟ (اختیاری)
                threading.Thread(target=scrape_all_channels).start()
            else:
                bale_send_message(chat_id, "این کانال قبلاً در لیست وجود دارد.")
        else:
            bale_send_message(chat_id, "❌ نام کاربری نامعتبر. لطفاً یک نام کاربری معتبر تلگرام (بدون @) ارسال کنید.")
    else:
        bale_send_message(chat_id, "از دکمه‌های منو استفاده کنید. برای شروع /start را بزنید.")

def run_bale_bot():
    """حلقه اصلی ربات بله (Polling)"""
    print("🤖 ربات بله راه‌اندازی شد...")
    last_update_id = 0
    while True:
        updates = bale_get_updates(offset=last_update_id+1)
        for update in updates:
            last_update_id = update["update_id"]
            if "callback_query" in update:
                cb = update["callback_query"]
                chat_id = cb["message"]["chat"]["id"]
                data = cb["data"]
                handle_callback(chat_id, data)
            elif "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                if text == "/start":
                    bale_send_message(chat_id, "به ربات مدیریت کانفیگ خوش آمدید! 🚀", keyboard=main_menu_keyboard())
                else:
                    handle_message(chat_id, text)
        time.sleep(1)

# ========== نقطه ورودی اصلی ==========
if __name__ == "__main__":
    # متغیر ساده برای نگهداری وضعیت انتظار کانال (در حافظه)
    global waiting_for_channel
    waiting_for_channel = {}
    
    # اگر آرگومان خط فرمان 'bot' داده شود، ربات بله اجرا می‌شود
    if len(sys.argv) > 1 and sys.argv[1] == "bot":
        run_bale_bot()
    else:
        # در غیر این صورت یکبار اسکرپ اجرا می‌شود (مناسب برای GitHub Actions)
        scrape_all_channels()
