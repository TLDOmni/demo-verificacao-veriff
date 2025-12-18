from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import requests
import json
import hashlib
import hmac
from datetime import datetime
import os

app = FastAPI()

# Modelo de dados que o Infobip vai enviar
class UserRequest(BaseModel):
    first_name: str
    last_name: str

# Configurações (Lidas das Variáveis de Ambiente do Servidor)
VERIFF_API_KEY = os.getenv("VERIFF_API_KEY")
VERIFF_SECRET_KEY = os.getenv("VERIFF_SECRET_KEY")
VERIFF_URL = "https://stationapi.veriff.com/v1/sessions"

def generate_signature(payload_str: str, secret: str) -> str:
    """Gera a assinatura HMAC exigida pela Veriff"""
    secret_bytes = bytes(secret, 'utf-8')
    payload_bytes = bytes(payload_str, 'utf-8')
    return hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()

@app.get("/")
def health_check():
    return {"status": "API Online 🚀"}

@app.post("/create-session")
def create_veriff_session(user: UserRequest):
    if not VERIFF_API_KEY or not VERIFF_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Chaves de API não configuradas.")

    # 1. Montar o Payload para a Veriff
    payload = {
        "verification": {
            "callback": "https://veriff.com", # Futuramente, seu webhook de retorno
            "person": {
                "firstName": user.first_name,
                "lastName": user.last_name
            },
            "document": {
                "type": "ID_CARD" 
            },
            "vendorData": str(datetime.now().timestamp())
        }
    }

    payload_json = json.dumps(payload)
    signature = generate_signature(payload_json, VERIFF_SECRET_KEY)

    headers = {
        "X-AUTH-CLIENT": VERIFF_API_KEY,
        "X-HMAC-SIGNATURE": signature,
        "Content-Type": "application/json"
    }

    # 2. Enviar requisição para a Veriff
    try:
        response = requests.post(VERIFF_URL, headers=headers, data=payload_json)
        response.raise_for_status() # Garante que erros 4xx/5xx sejam capturados
        
        data = response.json()
        
        # 3. Retornar apenas o link para o WhatsApp
        return {
            "status": "success",
            "verification_url": data["verification"]["url"]
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Erro Veriff: {e}")
        raise HTTPException(status_code=400, detail="Erro ao comunicar com a Veriff")