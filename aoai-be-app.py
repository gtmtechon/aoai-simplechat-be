from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import openai
import os
import uuid
import time
import json # JSON 파싱을 위해 추가

app = Flask(__name__)
CORS(app) # 모든 경로에 대해 CORS 허용

# --- Azure OpenAI Service 설정 ---
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
chat_histories = {}

# --- AOAI API 호출 함수 (지수 백오프 및 스트리밍 지원) ---
# 스트리밍 시에는 제너레이터를 반환합니다.
def call_aoai_with_retry(messages, stream=False, max_retries=5, initial_delay=1.0):
    delay = initial_delay
    for i in range(max_retries):
        try:
            response = openai.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=800,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stop=None,
                stream=stream # 스트리밍 활성화
            )
            return response # 스트림이면 제너레이터 객체, 아니면 응답 객체
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
                break
        except Exception as e:
            app.logger.error(f"알 수 없는 AOAI 호출 오류: {e}")
            break

        if i < max_retries - 1:
            time.sleep(delay)
            delay *= 2
    return None

# --- 챗봇 API 엔드포인트 (스트리밍 지원) ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    session_id = data.get('sessionId')

    if not user_message or not session_id:
        return jsonify({"error": "메시지 또는 세션 ID가 누락되었습니다."}), 400

    if session_id not in chat_histories:
        chat_histories[session_id] = [
            {"role": "system", "content": "You are a helpful and friendly assistant. Respond in Korean. Use markdown for formatting like **bold**, ### headers, and ```code``` blocks."},
            # 시스템 메시지: 마크다운 사용을 명시적으로 지시
        ]

    chat_histories[session_id].append({"role": "user", "content": user_message})

    def generate_stream():
        # AOAI 호출 (스트리밍 활성화)
        # 이 예제에서는 단순화를 위해 모든 기록을 전달합니다. 토큰 제한 고려 필요.
        stream_response = call_aoai_with_retry(chat_histories[session_id], stream=True)

        if stream_response is None:
            yield json.dumps({"error": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}) + "\n"
            return

        full_response_content = ""
        try:
            for chunk in stream_response:
                # 각 청크에서 델타 콘텐츠 추출
                content = chunk.choices[0].delta.content
                if content:
                    full_response_content += content
                    yield content # 프론트엔드로 직접 콘텐츠를 보냄
        except Exception as e:
            app.logger.error(f"스트리밍 중 오류 발생: {e}")
            yield json.dumps({"error": f"스트리밍 오류: {e}"}) + "\n"
        finally:
            # 스트림이 끝난 후 전체 응답을 대화 기록에 추가
            if session_id in chat_histories: # 세션이 아직 존재하는지 확인
                chat_histories[session_id].append({"role": "assistant", "content": full_response_content})

    # Event Stream (text/event-stream) 대신 일반 text/plain으로 단순화하여 직접 텍스트 청크를 보냄
    # 프론트엔드에서 SSE 파서 없이도 처리 가능하도록
    return Response(stream_with_context(generate_stream()), mimetype='text/plain')

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv('PORT', 8000))
