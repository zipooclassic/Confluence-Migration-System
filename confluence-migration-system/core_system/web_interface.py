import os
import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.orm import sessionmaker
from .database import SessionLocal, MigrationJob, PageMapping, ValidationJob, ValidationResult
from .confl_copier import ConfluenceAPI
from .migrate_manager import MigrationManager
from .page_validator import PageValidator

# Flask Blueprint 생성
# 템플릿 폴더의 상대 경로를 정확히 지정합니다.
web = Blueprint('web', __name__, template_folder='../web_templates/templates')

def get_db_session():
    """요청마다 새로운 DB 세션을 반환합니다."""
    return SessionLocal()

@web.route('/')
def dashboard():
    """대시보드 페이지. 모든 마이그레이션 작업을 보여줍니다."""
    db = get_db_session()
    jobs = db.query(MigrationJob).order_by(MigrationJob.id.desc()).all()
    db.close()
    return render_template('dashboard.html', jobs=jobs)

@web.route('/job/create', methods=['GET'])
def create_job_form():
    """새 마이그레이션 작업 생성 폼을 보여줍니다."""
    # .env 파일의 값을 폼에 미리 채우기 위해 전달
    env_vars = {
        "SOURCE_CONFLUENCE_URL": os.getenv("SOURCE_CONFLUENCE_URL"),
        "SOURCE_CONFLUENCE_USERNAME": os.getenv("SOURCE_CONFLUENCE_USERNAME"),
        "SOURCE_CONFLUENCE_API_TOKEN": os.getenv("SOURCE_CONFLUENCE_API_TOKEN"),
        "TARGET_CONFLUENCE_URL": os.getenv("TARGET_CONFLUENCE_URL"),
        "TARGET_CONFLUENCE_USERNAME": os.getenv("TARGET_CONFLUENCE_USERNAME"),
        "TARGET_CONFLUENCE_API_TOKEN": os.getenv("TARGET_CONFLUENCE_API_TOKEN"),
    }
    return render_template('create_job.html', env=env_vars)

def run_migration_in_background(form_data):
    """백그라운드에서 마이그레이션을 실행하는 함수."""
    db = get_db_session()
    try:
        source_api = ConfluenceAPI(form_data['source_url'], form_data['source_username'], form_data['source_api_token'])
        target_api = ConfluenceAPI(form_data['target_url'], form_data['target_username'], form_data['target_api_token'])
        manager = MigrationManager(source_api, target_api, db)
        manager.run_migration(form_data['source_root_page_id'], form_data['target_root_page_id'])
    except Exception as e:
        # 실제 운영 환경에서는 더 나은 오류 로깅 및 처리가 필요합니다.
        print(f"백그라운드 마이그레이션 작업 실패: {e}")
    finally:
        db.close()

@web.route('/job/create', methods=['POST'])
def create_job():
    """새 마이그레이션 작업을 시작합니다."""
    form_data = request.form.to_dict()

    # 백그라운드 스레드에서 마이그레이션 실행
    thread = threading.Thread(target=run_migration_in_background, args=(form_data,))
    thread.daemon = True
    thread.start()

    flash('마이그레이션 작업이 백그라운드에서 시작되었습니다. 대시보드에서 진행 상황을 확인하세요.', 'success')
    return redirect(url_for('web.dashboard'))

@web.route('/job/<int:job_id>')
def job_detail(job_id):
    """특정 마이그레이션 작업의 상세 정보를 보여줍니다."""
    db = get_db_session()
    job = db.query(MigrationJob).get(job_id)
    pages = db.query(PageMapping).filter_by(job_id=job_id).order_by(PageMapping.id).all()
    db.close()
    return render_template('job_detail.html', job=job, pages=pages)

def retry_job_in_background(job_id, form_data):
    """백그라운드에서 실패한 페이지 재시도를 실행하는 함수."""
    db = get_db_session()
    try:
        source_api = ConfluenceAPI(form_data['source_url'], form_data['source_username'], form_data['source_api_token'])
        target_api = ConfluenceAPI(form_data['target_url'], form_data['target_username'], form_data['target_api_token'])
        validator = PageValidator(source_api, target_api, db)
        validator.retry_failed_pages_for_job(job_id)
    except Exception as e:
        print(f"백그라운드 재시도 작업 실패: {e}")
    finally:
        db.close()

@web.route('/job/<int:job_id>/retry', methods=['POST'])
def retry_job(job_id):
    """실패한 페이지들을 재시도합니다."""
    # 재시도를 위해선 credential이 다시 필요합니다. 단순화를 위해 create_job과 같은 폼을 사용한다고 가정.
    # 실제 앱에서는 job 생성 시 credential을 암호화하여 저장하거나 다른 방식을 사용해야 합니다.
    # 여기서는 편의상 create_job_form과 유사한 숨겨진 필드나 세션에서 온다고 가정합니다.
    # 하지만 지금은 .env 에서 불러옵니다.
    form_data = {
        "source_url": os.getenv("SOURCE_CONFLUENCE_URL"),
        "source_username": os.getenv("SOURCE_CONFLUENCE_USERNAME"),
        "source_api_token": os.getenv("SOURCE_CONFLUENCE_API_TOKEN"),
        "target_url": os.getenv("TARGET_CONFLUENCE_URL"),
        "target_username": os.getenv("TARGET_CONFLUENCE_USERNAME"),
        "target_api_token": os.getenv("TARGET_CONFLUENCE_API_TOKEN"),
    }
    thread = threading.Thread(target=retry_job_in_background, args=(job_id, form_data))
    thread.daemon = True
    thread.start()

    flash(f'Job #{job_id}의 실패한 페이지에 대한 재시도 작업이 시작되었습니다.', 'info')
    return redirect(url_for('web.job_detail', job_id=job_id))

@web.route('/validation', methods=['GET'])
def validation_form():
    """검증 페이지를 보여줍니다. 과거의 검증 작업 리스트도 포함합니다."""
    db = get_db_session()
    validation_jobs = db.query(ValidationJob).order_by(ValidationJob.id.desc()).all()
    db.close()
    env_vars = {
        "SOURCE_CONFLUENCE_URL": os.getenv("SOURCE_CONFLUENCE_URL"),
        "SOURCE_CONFLUENCE_USERNAME": os.getenv("SOURCE_CONFLUENCE_USERNAME"),
        "SOURCE_CONFLUENCE_API_TOKEN": os.getenv("SOURCE_CONFLUENCE_API_TOKEN"),
        "TARGET_CONFLUENCE_URL": os.getenv("TARGET_CONFLUENCE_URL"),
        "TARGET_CONFLUENCE_USERNAME": os.getenv("TARGET_CONFLUENCE_USERNAME"),
        "TARGET_CONFLUENCE_API_TOKEN": os.getenv("TARGET_CONFLUENCE_API_TOKEN"),
    }
    return render_template('page_validation.html', validation_jobs=validation_jobs, env=env_vars)

def run_validation_in_background(form_data):
    """백그라운드에서 검증을 실행하는 함수."""
    db = get_db_session()
    try:
        source_api = ConfluenceAPI(form_data['source_url'], form_data['source_username'], form_data['source_api_token'])
        target_api = ConfluenceAPI(form_data['target_url'], form_data['target_username'], form_data['target_api_token'])
        validator = PageValidator(source_api, target_api, db)
        validator.validate_tree(form_data['source_root_id'], form_data['target_root_id'])
    except Exception as e:
        print(f"백그라운드 검증 작업 실패: {e}")
    finally:
        db.close()

@web.route('/validation/run', methods=['POST'])
def run_validation():
    """새 검증을 시작합니다."""
    form_data = request.form.to_dict()
    thread = threading.Thread(target=run_validation_in_background, args=(form_data,))
    thread.daemon = True
    thread.start()

    flash('페이지 트리 검증이 백그라운드에서 시작되었습니다.', 'success')
    return redirect(url_for('web.validation_form'))

@web.route('/validation/<int:validation_job_id>')
def validation_result(validation_job_id):
    """특정 검증 작업의 결과를 보여줍니다."""
    db = get_db_session()
    validation_job = db.query(ValidationJob).get(validation_job_id)
    results = db.query(ValidationResult).filter_by(validation_job_id=validation_job_id).all()
    db.close()
    return render_template('validation_result.html', validation_job=validation_job, results=results)
