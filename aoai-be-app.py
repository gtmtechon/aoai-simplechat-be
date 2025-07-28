from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import openai
import os
import uuid
import time
import json
from openai.error import OpenAIError  # OpenAI 오류 핸들링

app = Flask(__name__)
CORS(app)  # 모든 경로에 대해 CORS 허용

# --- Azure OpenAI Service 설정 ---
try:
    openai.api_type = "azure"
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai.api_version = "2024-12-01-preview"
    openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
    DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not all([openai.api_base, openai.api_key, DEPLOYMENT_NAME]):
        raise ValueError("Azure OpenAI Service 환경 변수가 설정되지 않았습니다.")
except Exception as e:
    app.logger.error(f"AOAI 초기화 오류: {e}")

# --- 인메모리 대화 기록 ---
chat_histories = {}

def call_aoai_with_retry(messages, stream=False, max_retries=5, initial_delay=1.0):
    delay = initial_delay
    for i in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=800,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stream=stream
            )
            return response
        except OpenAIError as e:
            if i < max_retries - 1:
                app.logger.warning(f"OpenAI API 오류 (시도 {i+1}/{max_retries}): {e}")
                time.sleep(delay)
                delay *= 2
            else:
                app.logger.error(f"OpenAI API 오류로 호출 실패: {e}")
    return None

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    session_id = data.get('sessionId')

    if not user_message or not session_id:
        return jsonify({"error": "메시지 또는 세션 ID가 누락되었습니다."}), 400

    if session_id not in chat_histories:
        chat_histories[session_id] = [
            {"role": "system", "content": "You are a helpful assistant. Use markdown for formatting such as **bold**, ### headers, and ```code``` blocks."}
        ]

    chat_histories[session_id].append({"role": "user", "content": user_message})

    def generate_stream():
        stream_response = call_aoai_with_retry(chat_histories[session_id], stream=True)

        if stream_response is None:
            yield json.dumps({"error": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}) + "\n"
            return

        full_response_content = ""
        try:
            for chunk in stream_response:
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if content:
                    full_response_content += content
                    yield content
        except Exception as e:
            app.logger.error(f"스트리밍 오류: {e}")
            yield json.dumps({"error": f"스트리밍 오류 발생: {str(e)}"}) + "\n"
        finally:
            if session_id in chat_histories:
                chat_histories[session_id].append({"role": "assistant", "content": full_response_content})

    return Response(stream_with_context(generate_stream()), mimetype='text/plain')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
