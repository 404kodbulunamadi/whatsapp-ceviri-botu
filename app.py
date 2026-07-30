from flask import Flask, request

app = Flask(__name__)

# Meta'nın webhook doğrulama adımı
@app.route('/webhook', methods=['GET'])
def verify():
    # Bu şifreyi birazdan Meta paneline gireceğiz
    verify_token = "BENIM_GIZLI_SIFREM" 
    
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return challenge, 200
        else:
            return 'Hatalı Token', 403
    return 'Merhaba, Webhook çalışıyor!', 200

# WhatsApp'tan gelen sesli mesajların düşeceği yer
@app.route('/webhook', methods=['POST'])
def receive_message():
    data = request.json
    print(data) # Gelen veriyi sunucu loglarında göreceğiz
    return 'EVENT_RECEIVED', 200
