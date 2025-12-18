from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel
import requests
import json
import hashlib
import hmac
from datetime import datetime
import os

app = FastAPI()

# --- CONFIGURAÇÕES (Variáveis de Ambiente) ---
VERIFF_API_KEY = os.getenv("VERIFF_API_KEY")
VERIFF_SECRET_KEY = os.getenv("VERIFF_SECRET_KEY")
VERIFF_URL = "https://stationapi.veriff.com/v1/sessions"

# Novas variáveis para a Infobip (Adicione no Render)
INFOBIP_API_KEY = os.getenv("INFOBIP_API_KEY") 
INFOBIP_BASE_URL = os.getenv("INFOBIP_BASE_URL") # Ex: https://j3k4m.api.infobip.com

# --- MODELOS DE DADOS ---
class UserRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str  # Novo campo: precisamos do telefone para o callback

# --- FUNÇÕES AUXILIARES ---
def generate_signature(payload_str: str, secret: str) -> str:
    secret_bytes = bytes(secret, 'utf-8')
    payload_bytes = bytes(payload_str, 'utf-8')
    return hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()

def send_whatsapp_message(to_phone: str, message_text: str):
    """Envia mensagem ativa via Infobip"""
    if not INFOBIP_API_KEY or not INFOBIP_BASE_URL:
        print("Erro: Credenciais Infobip não configuradas.")
        return

    url = f"{INFOBIP_BASE_URL}/whatsapp/1/message/text"
    headers = {
        "Authorization": f"App {INFOBIP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "from": "557133433406", # Substitua pelo SEU número de remetente Infobip
        "to": to_phone,
        "content": {"text": message_text}
    }
    
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"Falha ao enviar WhatsApp: {e}")

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "API Online e Pronta para Webhooks 🚀"}

@app.post("/create-session")
def create_veriff_session(user: UserRequest):
    # Payload para a Veriff
    payload = {
        "verification": {
            "callback": "https://veriff.com", 
            "person": {
                "firstName": user.first_name,
                "lastName": user.last_name
            },
            "document": {
                "type": "ID_CARD" 
            },
            # TRUQUE: Enviamos o telefone no vendorData para recuperá-lo depois
            "vendorData": user.phone 
        }
    }

    payload_json = json.dumps(payload)
    signature = generate_signature(payload_json, VERIFF_SECRET_KEY)

    headers = {
        "X-AUTH-CLIENT": VERIFF_API_KEY,
        "X-HMAC-SIGNATURE": signature,
        "Content-Type": "application/json"
    }

    resp = requests.post(VERIFF_URL, headers=headers, data=payload_json)
    
    if resp.status_code == 201:
        return {"status": "success", "verification_url": resp.json()["verification"]["url"]}
    else:
        raise HTTPException(status_code=400, detail="Erro ao criar sessão Veriff")

@app.post("/webhook/decision")
async def receive_veriff_decision(request: Request):
    """
    Este endpoint recebe o aviso da Veriff quando a análise termina.
    """
    try:
        body = await request.json()
        
        # 1. Validar Segurança (Verificar se veio mesmo da Veriff)
        # (Para simplificar, pulei a validação de assinatura aqui, 
        # mas em produção deve-se validar o X-HMAC-SIGNATURE do header)

        verification = body.get("verification", {})
        status = verification.get("status") # 'approved', 'declined', 'resubmission_requested'
        user_phone = verification.get("vendorData") # Recuperamos o telefone aqui!

        if not user_phone:
            return {"status": "ignored", "reason": "no phone found"}

        # 2. Tomar Decisão
        if status == "approved":
            msg = "✅ Parabéns! A sua identidade foi confirmada com sucesso. O seu cadastro está liberado."
            send_whatsapp_message(user_phone, msg)
            
        elif status == "declined":
            reason = verification.get("reason", "Motivo não especificado")
            msg = f"❌ A validação falhou. Motivo: {reason}. Por favor, tente novamente."
            send_whatsapp_message(user_phone, msg)
            
        elif status == "resubmission_requested":
             msg = "⚠️ A foto não ficou nítida. Por favor, reinicie o processo e tente novamente."
             send_whatsapp_message(user_phone, msg)

        return {"status": "processed", "decision": status}

    except Exception as e:
        print(f"Erro no webhook: {e}")
        return {"status": "error"}

