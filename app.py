import os
import requests
from flask import Flask, request

app = Flask(__name__)

# --- AYARLAR ---
VERIFY_TOKEN = "BENIM_GIZLI_SIFREM"
PHONE_NUMBER_ID = "1234105529794933" 

# Şifreleri açıkça yazmıyoruz, Render'ın güvenli ayarlarından (Environment) çekiyoruz:
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
            return challenge, 200
        return 'Hatalı Token', 403
        
    elif request.method == 'POST':
        body = request.json
        try:
            if body.get('object'):
                entry = body['entry'][0]
                changes = entry['changes'][0]
                value = changes['value']
                
                if 'messages' in value:
                    message = value['messages'][0]
                    sender_phone = message['from']
                    
                    if message['type'] == 'audio':
                        audio_id = message['audio']['id']
                        send_message(sender_phone, "🐱 Sesli mesajını aldım, metne döküp Türkçeye çeviriyorum...")
                        process_audio(audio_id, sender_phone)
        except Exception as e:
            print("Webhook işleme hatası:", e)
            
        return 'OK', 200

def process_audio(audio_id, sender_phone):
    try:
        url_req = requests.get(
            f"https://graph.facebook.com/v25.0/{audio_id}", 
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        media_url = url_req.json().get("url")
        
        audio_req = requests.get(
            media_url, 
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
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
        
        transcribed_text = transcribe_res.json().get("text", "")
        
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
            turkish_text = translate_res.json()["choices"][0]["message"]["content"]
            final_message = f"🗣️ *Orijinal Metin:*\n_{transcribed_text}_\n\n🇹🇷 *Çeviri:*\n*{turkish_text}*"
        else:
            final_message = "❌ Seste herhangi bir konuşma algılayamadım."
            
        send_message(sender_phone, final_message)
        
    except Exception as e:
        print("İşlem hatası:", e)
        send_message(sender_phone, "⚠️ Çeviri motorunda bir hata oluştu, lütfen daha sonra tekrar dene.")

def send_message(to, text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
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
    requests.post(url, headers=headers, json=data)

if __name__ == '__main__':
    app.run(port=5000)
