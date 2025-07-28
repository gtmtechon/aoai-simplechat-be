# aoai-simplechat-be
simple chat application on aoai
환경 변수 설정:

생성된 App Service로 이동하여 좌측 메뉴의 구성(Configuration) -> 애플리케이션 설정(Application settings)으로 이동합니다.

새 애플리케이션 설정(New application setting)을 클릭하여 다음 키-값 쌍을 추가합니다.

AZURE_OPENAI_API_KEY: 1단계에서 복사한 AOAI API 키

AZURE_OPENAI_ENDPOINT: 1단계에서 복사한 AOAI 엔드포인트 URL

AZURE_OPENAI_DEPLOYMENT_NAME: 1단계에서 배포한 모델의 이름 (예: gpt-35-turbo-chatbot)

WEBSITES_PORT: 8000 (Flask 앱이 8000번 포트에서 실행되므로 설정 필요)

WEBSITES_ENABLE_APP_SERVICE_STORAGE: false (컨테이너 앱이므로 불필요한 스토리지 마운트 방지)

PYTHON_ENABLE_ONLINE_BUILD: true (App Service에서 빌드를 수행하도록 설정)

Startup Command: gunicorn --bind 0.0.0.0 --timeout 600 --workers 2 app:app (Gunicorn을 사용하여 Flask 앱 실행. app:app은 app.py 파일 내의 Flask 앱 인스턴스 이름이 app임을 의미합니다. 필요시 workers 수를 조정할 수 있습니다.)

저장을 클릭합니다.




=============
pip install -r requirements.txt
uvicorn main:app --reload