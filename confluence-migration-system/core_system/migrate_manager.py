import logging
from sqlalchemy.orm import Session
from . import database as db
from .confl_copier import ConfluenceAPI

# 로깅 설정
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class MigrationManager:
    """
    소스에서 타겟 Confluence 인스턴스로 페이지 마이그레이션 프로세스를 총괄합니다.
    """

    def __init__(self, source_api: ConfluenceAPI, target_api: ConfluenceAPI, db_session: Session):
        """
        MigrationManager를 초기화합니다.

        :param source_api: 소스용 ConfluenceAPI 인스턴스.
        :param target_api: 타겟용 ConfluenceAPI 인스턴스.
        :param db_session: SQLAlchemy 세션 객체.
        """
        self.source_api = source_api
        self.target_api = target_api
        self.db = db_session

    def _get_target_parent_id(self, job: db.MigrationJob, source_page: dict) -> str | None:
        """
        주어진 소스 페이지에 대해 타겟 시스템에서 올바른 상위 페이지 ID를 결정합니다.

        :param job: 현재 MigrationJob 객체.
        :param source_page: Confluence API에서 온 소스 페이지 딕셔너리.
        :return: 타겟 상위 페이지 ID 문자열, 또는 루트 페이지인 경우 None.
        """
        # 직계 부모는 조상 리스트의 마지막 항목입니다.
        if not source_page.get('ancestors'):
            # 이 페이지는 조상이 없으므로, 부모는 마이그레이션 루트입니다.
            return job.target_root_page_id

        direct_parent_summary = source_page['ancestors'][-1]
        source_parent_id = direct_parent_summary['id']

        # 소스 부모가 마이그레이션의 루트이면, 새 부모는 타겟 루트입니다.
        if source_parent_id == job.source_root_page_id:
            return job.target_root_page_id

        # 그렇지 않으면, 데이터베이스 매핑에서 부모의 새 ID를 조회합니다.
        parent_mapping = self.db.query(db.PageMapping).filter_by(
            job_id=job.id,
            source_page_id=source_parent_id
        ).first()

        if parent_mapping and parent_mapping.status == 'SUCCESS':
            return parent_mapping.target_page_id
        else:
            # 페이지를 순서대로 처리하면 이 경우는 드물지만, 안전 장치입니다.
            log.warning(f"부모 페이지 {source_parent_id}에 대한 성공적인 매핑을 찾을 수 없습니다. "
                        f"페이지 '{source_page['title']}'이(가) 고아 페이지가 될 수 있습니다.")
            return None

    def run_migration(self, source_root_page_id: str, target_root_page_id: str):
        """
        주어진 페이지 트리에 대해 전체 마이그레이션을 실행합니다.

        :param source_root_page_id: 소스 Confluence의 루트 페이지 ID.
        :param target_root_page_id: 새 트리가 생성될 타겟 Confluence의 페이지 ID.
        :return: 생성된 MigrationJob 객체.
        """
        log.info(f"소스 페이지 {source_root_page_id}에서 타겟 페이지 {target_root_page_id}로 마이그레이션을 시작합니다.")

        # 1. DB에 새 MigrationJob 생성
        job = db.MigrationJob(
            source_root_page_id=source_root_page_id,
            target_root_page_id=target_root_page_id,
            status='PENDING'
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        log.info(f"ID가 {job.id}인 MigrationJob을 생성했습니다.")

        try:
            # 2. 소스에서 모든 페이지 가져오기
            job.status = 'FETCHING'
            self.db.commit()

            # 사용자는 소스 페이지 자체가 아닌, 해당 페이지의 모든 *하위* 페이지만을 마이그레이션 하기를 원합니다.
            # 따라서 하위 페이지만 가져오면 됩니다.
            log.info(f"소스 페이지 {source_root_page_id}의 하위 페이지를 가져옵니다...")
            all_pages_to_migrate = self.source_api.get_all_descendants(source_root_page_id)

            # get_all_descendants는 직계 자식부터 시작하므로, 소스 루트 페이지 자체를 확인할 필요는 없습니다.
            # get_page를 호출하여 페이지 존재 여부만 확인합니다.
            if not self.source_api.get_page(source_root_page_id):
                 raise ValueError(f"소스 루트 페이지 {source_root_page_id}를 찾을 수 없거나 접근할 수 없습니다.")

            if not all_pages_to_migrate:
                log.warning(f"소스 페이지 {source_root_page_id}에 마이그레이션할 하위 페이지가 없습니다.")

            job.total_pages = len(all_pages_to_migrate)
            log.info(f"총 {job.total_pages}개의 페이지를 마이그레이션합니다.")

            # 3. PageMapping 테이블 미리 채우기
            for page_data in all_pages_to_migrate:
                parent = page_data['ancestors'][-1] if page_data.get('ancestors') else {}
                mapping = db.PageMapping(
                    job_id=job.id,
                    source_page_id=page_data['id'],
                    source_page_title=page_data['title'],
                    source_parent_id=parent.get('id'),
                    status='PENDING'
                )
                self.db.add(mapping)
            self.db.commit()
            log.info("데이터베이스에 페이지 매핑을 미리 채웠습니다.")

            # 4. 각 페이지 처리
            job.status = 'RUNNING'
            self.db.commit()

            target_space_key = self.target_api.get_space_key_from_page(target_root_page_id)
            if not target_space_key:
                raise RuntimeError(f"타겟 페이지 {target_root_page_id}의 스페이스 키를 확인할 수 없습니다.")

            for page_data in all_pages_to_migrate:
                mapping = self.db.query(db.PageMapping).filter_by(job_id=job.id, source_page_id=page_data['id']).first()
                try:
                    target_parent_id = self._get_target_parent_id(job, page_data)
                    if not target_parent_id:
                        raise Exception("타겟 상위 ID를 결정할 수 없습니다.")

                    log.info(f"페이지 처리 중: '{page_data['title']}' (소스 ID: {page_data['id']})")

                    # 타겟에 페이지 생성
                    new_page = self.target_api.create_page(
                        space_key=target_space_key,
                        title=page_data['title'],
                        body=page_data['body']['storage']['value'],
                        parent_id=target_parent_id
                    )

                    # 성공 시 DB 업데이트
                    mapping.target_page_id = new_page['id']
                    mapping.target_parent_id = target_parent_id
                    mapping.status = 'SUCCESS'
                    job.successful_pages += 1
                    log.info(f"페이지 '{page_data['title']}'를 성공적으로 마이그레이션했습니다. 새 ID: {new_page['id']}")

                except Exception as e:
                    error_msg = f"페이지 '{page_data['title']}' 마이그레이션 실패: {e}"
                    log.error(error_msg)
                    mapping.status = 'FAILED'
                    mapping.error_message = error_msg
                    job.failed_pages += 1

                self.db.commit()

            # 5. 작업 마무리
            job.status = 'COMPLETED' if job.failed_pages == 0 else 'COMPLETED_WITH_ERRORS'
            self.db.commit()
            log.info(f"마이그레이션 작업 {job.id}이(가) 상태 '{job.status}'로 완료되었습니다.")

        except Exception as e:
            job.status = 'FAILED'
            job.error_message = str(e)
            self.db.commit()
            log.critical(f"마이그레이션 작업 {job.id}이(가) 치명적인 오류로 실패했습니다: {e}")

        return job
