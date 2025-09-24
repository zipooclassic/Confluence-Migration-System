import os
from flask import Flask, redirect, url_for
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
# 이 코드는 Flask 앱이 생성되기 전에 실행되어야 합니다.
load_dotenv()

# core_system에서 필요한 모듈과 블루프린트를 임포트합니다.
from core_system.web_interface import web
from core_system.database import init_db

def create_app():
    """
    Flask 애플리케이션을 생성하고 설정합니다.
    """
    # Flask 앱 인스턴스 생성
    # static_folder와 static_url_path를 web_templates/static으로 지정합니다.
    app = Flask(__name__,
                static_folder='web_templates/static',
                static_url_path='/static')

    # 환경 변수에서 시크릿 키 설정
    # .env 파일에 `SECRET_KEY`가 정의되어 있어야 합니다.
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_default_secret_key_for_development')

    # 데이터베이스 초기화
    # 앱 시작 시 한 번만 실행되도록 합니다.
    # init_db() 함수는 이미 테이블이 존재하면 새로 만들지 않습니다.
    with app.app_context():
        init_db()

    # 블루프린트 등록
    app.register_blueprint(web)

    @app.route('/')
    def index():
        # 루트 URL을 대시보드로 리디렉션합니다.
        return redirect(url_for('web.dashboard'))

    return app

app = create_app()

def main():
    """콘솔 스크립트 진입점 또는 직접 실행시 사용됩니다."""
    # Gunicorn과 같은 프로덕션 서버를 사용할 때는 이 함수가 직접 호출되지 않습니다.
    # 개발 환경에서 직접 실행할 때 사용됩니다.
    # host='0.0.0.0'은 외부에서도 접근 가능하게 합니다.
    app.run(debug=False, host='0.0.0.0', port=5001)


if __name__ == '__main__':
    main()
