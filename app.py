import os
import requests
from flask import Flask, request

app = Flask(__name__)

# --- AYARLAR ---
VERIFY_TOKEN = "BENIM_GIZLI_SIFREM"
PHONE_NUMBER_ID = "1234105529794933"
API_VERSION = "v25.0"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
# ---------------

# Kullanıcı numarasına göre seçili dili tutan basit hafıza
# NOT: Render sunucusu yeniden başladığında (uykuya girip çıktığında) bu bilgi sıfırlanır
user_languages = {}

# Desteklenen diller: komut kelimesi -> (görünen isim, prompt için İngilizce isim, emoji)
LANGUAGES = {
    "türkçe":     ("Türkçe", "Turkish", "🇹🇷"),
    "ingilizce":  ("İngilizce", "English", "🇬🇧"),
    "ispanyolca": ("İspanyolca", "Spanish", "🇪🇸"),
    "almanca":    ("Almanca", "German", "🇩🇪"),
    "fransızca":  ("Fransızca", "French", "🇫🇷"),
    "italyanca":  ("İtalyanca", "Italian", "🇮🇹"),
    "portekizce": ("Portekizce", "Portuguese", "🇵🇹"),
    "rusça":      ("Rusça", "Russian", "🇷🇺"),
    "arapça":     ("Arapça", "Arabic", "🇸🇦"),
    "japonca":    ("Japonca", "Japanese", "🇯🇵"),
}

DEFAULT_LANG = "türkçe"


@app.route('/ping', methods=['GET'])
def ping():
    return 'OK', 200


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("🟢 Webhook başarıyla doğrulandı!", flush=True)
            return challenge, 200
        return 'Hatalı Token', 403

    elif request.method == 'POST':
        body = request.get_json(silent=True) or {}
        print("📩 YENİ BİLDİRİM GELDİ:", body, flush=True)

        try:
            if body.get('object'):
                entry = body['entry'][0]
                changes = entry['changes'][0]
                value = changes['value']

                if 'messages' in value:
                    message = value['messages'][0]
                    sender_phone = message['from']
                    msg_type = message.get('type')

                    print(f"📱 Mesaj Tipi: {msg_type} | Gönderen: {sender_phone}", flush=True)

                    if msg_type in ['audio', 'voice']:
                        audio_id = message[msg_type]['id']
                        target_lang = user_languages.get(sender_phone, DEFAULT_LANG)
                        lang_display = LANGUAGES[target_lang][0]
                        send_message(sender_phone, f"🐱 Sesli mesajını aldım, {lang_display}ye çeviriyorum...")
                        process_audio(audio_id, sender_phone, target_lang)

                    elif msg_type == 'text':
                        text_body = message['text']['body'].strip()
                        handle_text_message(text_body, sender_phone)

        except Exception as e:
            print("❌ Webhook işleme hatası:", e, flush=True)

        return 'OK', 200


def handle_text_message(text, sender_phone):
    lower_text = text.lower()

    # 1. Dil değiştirme komutu: "dil ingilizce"
    if lower_text.startswith("dil "):
        lang_word = lower_text.replace("dil ", "").strip()
        if lang_word in LANGUAGES:
            user_languages[sender_phone] = lang_word
            lang_display, _, emoji = LANGUAGES[lang_word]
            send_message(sender_phone, f"✅ Çeviri dilini {emoji} {lang_display} olarak ayarladım!")
        else:
            available = ", ".join(LANGUAGES.keys())
            send_message(sender_phone, f"❌ Bu dili tanımıyorum. Desteklenen diller:\n{available}")
        return

    # 2. Yardım / dil listesi komutu
    if lower_text in ["diller", "dil listesi", "yardım", "help"]:
        available = "\n".join([f"• {k}" for k in LANGUAGES.keys()])
        current = user_languages.get(sender_phone, DEFAULT_LANG)
        send_message(sender_phone,
            f"🌍 Şu an çeviri dilin: {LANGUAGES[current][0]}\n\n"
            f"Değiştirmek için 'dil <isim>' yaz. Örnek: dil ingilizce\n\n"
            f"Desteklenen diller:\n{available}\n\n"
            f"🎤 Bana bir sesli mesaj ya da yazı gönder, çevireyim!")
        return

    # 3. Bunların dışındaki her metin: doğrudan çevrilir
    target_lang = user_languages.get(sender_phone, DEFAULT_LANG)
    translate_and_send(text, sender_phone, target_lang, is_audio=False)


def process_audio(audio_id, sender_phone, target_lang):
    try:
        print(f"🎙️ Ses işleniyor ID: {audio_id}", flush=True)

        url_req = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{audio_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        url_data = url_req.json()
        media_url = url_data.get("url")

        if not media_url:
            print("❌ Medya URL'si alınamadı! Yanıt:", url_data, flush=True)
            return

        audio_req = requests.get(
            media_url,
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        )

        if audio_req.status_code != 200:
            print(f"❌ Ses dosyası indirilemedi! Status Code: {audio_req.status_code}", flush=True)
            return

        file_path = "temp_audio.ogg"
        with open(file_path, "wb") as f:
            f.write(audio_req.content)

        with open(file_path, "rb") as f:
            transcribe_res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (file_path, f, "audio/ogg")},
                data={"model": "whisper-large-v3"}
            )

        transcribe_json = transcribe_res.json()
        transcribed_text = transcribe_json.get("text", "")
        print(f"📝 Deşifre Metin: {transcribed_text}", flush=True)

        if not transcribed_text:
            send_message(sender_phone, "❌ Seste herhangi bir konuşma algılayamadım.")
            return

        translate_and_send(transcribed_text, sender_phone, target_lang, is_audio=True)

    except Exception as e:
        print("❌ İşlem hatası:", e, flush=True)
        send_message(sender_phone, "⚠️ Çeviri motorunda bir hata oluştu, lütfen daha sonra tekrar dene.")


def translate_and_send(source_text, sender_phone, target_lang, is_audio):
    try:
        lang_display, lang_prompt, emoji = LANGUAGES[target_lang]

        translate_res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": f"Sen profesyonel bir dil uzmanı ve eğitimcisin. Kullanıcının sana gönderdiği metni en doğal, akıcı ve gramer açısından kusursuz bir {lang_prompt} diline çevir. Ekstra hiçbir açıklama veya yorum ekleme, sadece çeviriyi ver."},
                    {"role": "user", "content": source_text}
                ]
            }
        )
        translate_json = translate_res.json()

        if "choices" in translate_json and len(translate_json["choices"]) > 0:
            translated_text = translate_json["choices"][0]["message"]["content"]
            if is_audio:
                final_message = f"🗣️ *Orijinal Metin:*\n_{source_text}_\n\n{emoji} *Çeviri ({lang_display}):*\n*{translated_text}*"
            else:
                final_message = f"{emoji} *Çeviri ({lang_display}):*\n{translated_text}"
        else:
            print("❌ Groq Çeviri Hatası:", translate_json, flush=True)
            final_message = "⚠️ Çeviri yapılırken bir API hatası oluştu."

        send_message(sender_phone, final_message)
        print("✅ Yanıt başarıyla gönderildi!", flush=True)

    except Exception as e:
        print("❌ Çeviri hatası:", e, flush=True)
        send_message(sender_phone, "⚠️ Çeviri motorunda bir hata oluştu, lütfen daha sonra tekrar dene.")


def send_message(to, text):
    url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    res = requests.post(url, headers=headers, json=data)
    if res.status_code != 200:
        print("❌ Mesaj gönderme hatası:", res.json(), flush=True)


if __name__ == '__main__':
    app.run(port=5000)
