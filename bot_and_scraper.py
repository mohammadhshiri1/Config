#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import hashlib
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ========== تنظیمات ==========
DATA_FILE = "data.json"
PATTERNS = {
    "vmess": r"vmess://[A-Za-z0-9+/=]+",
    "vless": r"vless://[A-Za-z0-9+/=]+@[^\s]+",
    "trojan": r"trojan://[A-Za-z0-9@.]+",
    "ss": r"ss://[A-Za-z0-9@.]+",
    "hysteria2": r"hysteria2://[A-Za-z0-9@.]+",
    "tuic": r"tuic://[A-Za-z0-9@.]+"
}

# ========== توابع داده ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "channels": {"list": [], "auto_add_pending": {}},
        "database": {"configs": [], "last_seen": {}},
        "status": {"active": True},
        "stats": {"total_configs": 0, "last_update": None}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ========== توابع اسکرپ ==========
def get_post_texts(channel_username, limit=10):
    url = f"https://t.me/s/{channel_username}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        return [msg.get_text(strip=True) for msg in messages[:limit]]
    except Exception as e:
        print(f"⚠️ خطا در {channel_username}: {e}")
        return []

def extract_configs_from_text(text):
    configs = []
    for proto, pattern in PATTERNS.items():
        for m in re.findall(pattern, text):
            configs.append({
                "raw": m,
                "type": proto,
                "hash": hashlib.md5(m.encode()).hexdigest()
            })
    return configs

def update_database(channel, new_configs, data):
    db_configs = data["database"]["configs"]
    added = 0
    for cfg in new_configs:
        if not any(ex["hash"] == cfg["hash"] for ex in db_configs):
            cfg["channel"] = channel
            cfg["timestamp"] = time.time()
            db_configs.append(cfg)
            added += 1
    data["database"]["last_seen"][channel] = time.time()
    unique_hashes = set(c["hash"] for c in db_configs)
    data["stats"]["total_configs"] = len(unique_hashes)
    return added

def generate_subscription_link(data):
    if not data["status"]["active"]:
        with open("subscription.txt", "w", encoding="utf-8") as f:
            f.write("# ربات موقتاً غیر فعال شده است\n")
            f.write("vmess://eyJhZGQiOiJEZW1vIiwicG9ydCI6IjQ0MyIsInR5cGUiOiJub25lIn0=")
        return

    all_configs = data["database"]["configs"]
    all_configs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    unique = []
    seen = set()
    for cfg in all_configs:
        if cfg["hash"] not in seen:
            seen.add(cfg["hash"])
            unique.append(cfg)
    final = unique[:50]

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
    pending = data["channels"].get("auto_add_pending", {})
    now_ts = time.time()
    to_add = []
    for cand, first_seen in list(pending.items()):
        if now_ts - first_seen > 10800:
            texts = get_post_texts(cand, limit=5)
            has_config = any(extract_configs_from_text(t) for t in texts)
            if has_config:
                to_add.append(cand)
            del pending[cand]
    for cand in to_add:
        if cand not in data["channels"]["list"]:
            data["channels"]["list"].append(cand)
            print(f"✅ کانال خودکار اضافه شد: {cand}")
    if to_add:
        data["channels"]["auto_add_pending"] = pending
        save_data(data)

def scrape_all_channels():
    print("🔄 شروع اسکرپ...")
    data = load_data()
    for ch in data["channels"]["list"]:
        print(f"🔍 اسکرپ {ch}")
        texts = get_post_texts(ch, limit=10)
        all_new = []
        for text in texts:
            all_new.extend(extract_configs_from_text(text))
        added = update_database(ch, all_new, data)
        print(f"   ➕ {added} کانفیگ جدید")
        # استخراج لینک کانال‌های دیگر برای auto-add
        for text in texts:
            found = re.findall(r"t\.me/([a-zA-Z][a-zA-Z0-9_]{4,})", text)
            for new_ch in found:
                if new_ch not in data["channels"]["list"] and new_ch not in data["channels"].get("auto_add_pending", {}):
                    data["channels"].setdefault("auto_add_pending", {})[new_ch] = time.time()
                    save_data(data)
    auto_add_channels(data)
    data = load_data()
    generate_subscription_link(data)
    save_data(data)
    print("✅ اسکرپ پایان یافت")

if __name__ == "__main__":
    scrape_all_channels()
