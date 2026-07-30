import os
import requests
from flask import Flask, request

app = Flask(__name__)

# --- AYARLAR ---
VERIFY_TOKEN = "BENIM_GIZLI_SIFREM"
PHONE_NUMBER_ID = "1234105529794933"
API_VERSION = "v25.0"  # Meta Panelindeki güncel Graph API sürümü

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
# ---------------

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
                    
                    # Hem mikrofon ses kayıtlarını (voice) hem ses dosyalarını (audio) yakalıyoruz
                    if msg_type in ['audio', 'voice']:
                        audio_id = message[msg_type]['id']
                        send_message(sender_phone, "🐱 Sesli mesajını aldım, metne döküp Türkçeye çeviriyorum...")
                        process_audio(audio_id, sender_phone)
                    elif msg_type == 'text':
                        send_message(sender_phone, "🐱 Lütfen bana çevirmem için bir ses kaydı gönder!")
                        
        except Exception as e:
            print("❌ Webhook işleme hatası:", e, flush=True)
            
        return 'OK', 200

def process_audio(audio_id, sender_phone):
    try:
        print(f"🎙️ Ses işleniyor ID: {audio_id}", flush=True)
        
        # 1. Medya URL'sini Meta Graph API'den İsteme
        url_req = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{audio_id}", 
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        url_data = url_req.json()
        media_url = url_data.get("url")
        
        if not media_url:
            print("❌ Medya URL'si alınamadı! Yanıt:", url_data, flush=True)
            return

        # 2. Ses Dosyasını İndirme (User-Agent ile Meta engellerini aşma)
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
            
        # 3. Groq Whisper ile Sesi Metne Çevirme
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
        
        # 4. Metni Llama 3 ile Türkçeye Çevirme
        if transcribed_text:
            translate_res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama3-70b-8192",
                    "messages": [
                        {"role": "system", "content": "Sen profesyonel bir dil uzmanı ve eğitimcisin. Kullanıcının sana gönderdiği metni (özellikle İspanyolca veya Portekizce olabilir) en doğal, akıcı ve gramer açısından kusursuz bir Türkçeye çevir. Ekstra hiçbir açıklama veya yorum ekleme, sadece çeviriyi ver."},
                        {"role": "user", "content": transcribed_text}
                    ]
                }
            )
            translate_json = translate_res.json()
            
            if "choices" in translate_json and len(translate_json["choices"]) > 0:
                turkish_text = translate_json["choices"][0]["message"]["content"]
                final_message = f"🗣️ *Orijinal Metin:*\n_{transcribed_text}_\n\n🇹🇷 *Çeviri:*\n*{turkish_text}*"
            else:
                print("❌ Groq Çeviri Hatası:", translate_json, flush=True)
                final_message = "⚠️ Çeviri yapılırken bir API hatası oluştu."
        else:
            final_message = "❌ Seste herhangi bir konuşma algılayamadım."
            
        send_message(sender_phone, final_message)
        print("✅ Yanıt başarıyla gönderildi!", flush=True)
        
    except Exception as e:
        print("❌ İşlem hatası:", e, flush=True)
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
