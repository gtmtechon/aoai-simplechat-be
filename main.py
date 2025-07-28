from fastapi import FastAPI, HTTPException, Request
from flask_cors import CORS
from pydantic import BaseModel
import openai
import os

# 환경변수 또는 직접 입력 (보안 상 권장: 환경변수)
openai.api_type = "azure"
openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT", "https://<your-resource-name>.openai.azure.com")
openai.api_version = "2024-11-20"  # 최신 버전 확인 필요
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

# FastAPI 초기화
app = FastAPI()
CORS(app) # 모든 경로에 대해 CORS 허용

# CORS 설정 (필요시 수정)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # 배포 시에는 도메인 제한 권장
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# 요청 형식 정의
class ChatRequest(BaseModel):
    message: str

# 응답 형식 정의
class ChatResponse(BaseModel):
    response: str

# 루트 확인용
@app.get("/")
def read_root():
    return {"message": "Azure OpenAI FastAPI 백엔드 작동 중"}

# 챗 요청 처리
@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        messages = [{"role": "user", "content": req.message}]
        completion = openai.ChatCompletion.create(
            engine=deployment_name,
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )
        reply = completion['choices'][0]['message']['content']
        return {"response": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))