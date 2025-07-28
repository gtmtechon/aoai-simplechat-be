# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS # CORS 문제를 해결하기 위해 Flask-CORS 라이브러리 사용
import openai
import os
import uuid
import time # 지수 백오프를 위한 time 모듈 추가

app = Flask(__name__)

FRONTEND_ORIGINS = [
    "https://victorious-forest-0bfc54200.2.azurestaticapps.net",
    "http://localhost:3000"  # 로컬 개발용
    # 필요하다면 다른 개발/테스트 Origin도 추가
    # 다른 Origin이 있다면 추가
]
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGINS}})

CORS(app) # 모든 경로에 대해 CORS 허용

# --- Azure OpenAI Service 설정 ---
# 환경 변수에서 API 키와 엔드포인트 로드 (보안을 위해 Key Vault 사용 권장)
# Azure App Service에 배포 시, 구성(Configuration) -> 애플리케이션 설정(Application settings)에서 설정합니다.
# 예: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME
try:
    openai.api_type = "azure"
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai.api_version = "2024-02-15-preview" # 최신 API 버전 확인 및 업데이트
    openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
    DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not all([openai.api_base, openai.api_key, DEPLOYMENT_NAME]):
        raise ValueError("Azure OpenAI Service 환경 변수가 설정되지 않았습니다.")
except Exception as e:
    app.logger.error(f"AOAI 초기화 오류: {e}")
    # 프로덕션 환경에서는 앱 시작 실패 처리 또는 기본 응답 설정

# --- 인메모리 대화 기록 (간단한 세션 관리) ---
# 이 방식은 서버 재시작 시 데이터가 사라집니다.
# 프로덕션 환경에서는 Azure Cosmos DB와 같은 영구 데이터베이스를 사용해야 합니다.
chat_histories = {}

# --- AOAI API 호출 함수 (지수 백오프 포함) ---
def call_aoai_with_retry(messages, max_retries=5, initial_delay=1.0):
    delay = initial_delay
    for i in range(max_retries):
        try:
            response = openai.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.7, # 창의성 조절 (0.0-1.0)
                max_tokens=800, # 최대 응답 길이
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stop=None
            )
            return response.choices[0].message.content
        except openai.APITimeoutError as e:
            app.logger.warning(f"AOAI API 호출 시간 초과 (시도 {i+1}/{max_retries}): {e}")
        except openai.APIConnectionError as e:
            app.logger.warning(f"AOAI API 연결 오류 (시도 {i+1}/{max_retries}): {e}")
        except openai.APIStatusError as e:
            app.logger.warning(f"AOAI API 상태 오류 (시도 {i+1}/{max_retries}): {e}")
            if e.status_code == 429: # Too Many Requests
                app.logger.warning(f"Too Many Requests (429), 재시도 예정. 지연: {delay}초")
            else:
                app.logger.error(f"예상치 못한 AOAI API 오류 (상태 코드: {e.status_code}): {e}")
                break # 429 외 다른 치명적인 오류는 재시도하지 않음
        except Exception as e:
            app.logger.error(f"알 수 없는 AOAI 호출 오류: {e}")
            break # 알 수 없는 오류는 재시도하지 않음

        if i < max_retries - 1:
            time.sleep(delay)
            delay *= 2 # 지수 백오프 (2배 증가)
    return None # 모든 재시도 실패

# --- 챗봇 API 엔드포인트 ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    session_id = data.get('sessionId')

    if not user_message or not session_id:
        return jsonify({"error": "메시지 또는 세션 ID가 누락되었습니다."}), 400

    # 세션 ID를 사용하여 대화 기록 가져오기
    # 새로운 세션이면 빈 리스트 초기화
    if session_id not in chat_histories:
        chat_histories[session_id] = [
            {"role": "system", "content": "You are a helpful and friendly assistant. Respond in Korean."}
        ]
        # 시스템 메시지는 최초 1회만 추가 (새로운 세션일 경우)

    # 사용자 메시지를 대화 기록에 추가
    chat_histories[session_id].append({"role": "user", "content": user_message})

    try:
        # AOAI 호출 (대화 기록 전달)
        # AOAI의 토큰 제한에 유의하며, 너무 긴 대화 기록은 잘라내야 할 수 있습니다.
        # 이 예제에서는 단순화를 위해 모든 기록을 전달합니다.
        aoai_response_content = call_aoai_with_retry(chat_histories[session_id])

        if aoai_response_content is None:
            return jsonify({"error": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}), 500

        # AI 응답을 대화 기록에 추가
        chat_histories[session_id].append({"role": "assistant", "content": aoai_response_content})

        return jsonify({"response": aoai_response_content})

    except Exception as e:
        app.logger.error(f"챗봇 처리 중 오류 발생: {e}")
        return jsonify({"error": "챗봇 서비스에 문제가 발생했습니다. 관리자에게 문의하세요."}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # 로컬 테스트를 위한 실행 (프로덕션에서는 Gunicorn 등 WSGI 서버 사용)
    # App Service는 Gunicorn을 자동으로 사용합니다.
    app.run(host='0.0.0.0', port=os.getenv('PORT', 8000))
