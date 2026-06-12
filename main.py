from fastapi import FastAPI
app = FastAPI()

from fastapi import FastAPI
from pydantic import BaseModel
 
app = FastAPI()
 
class ChatRequest(BaseModel):
    message: str
 
@app.get("/")
def root():
    return {"message": "Oylan assistant is running!"}
@app.get("/health")
def health():
    return {"health": "ok"}
 
@app.post("/chat")
def chat(req: ChatRequest):
    # пока возвращаем эхо; настоящий Oylan подключим позже
    return {"reply": f"You said: {req.message}"}