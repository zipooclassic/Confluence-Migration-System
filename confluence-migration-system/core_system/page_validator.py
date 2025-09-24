import logging
from sqlalchemy.orm import Session
from . import database as db
from .confl_copier import ConfluenceAPI
from .migrate_manager import MigrationManager # 일부 로직 재사용 가능

# 로깅 설정
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class PageValidator:
    """
    마이그레이션된 콘텐츠의 검증 및 실패한 페이지의 재시도를 처리합니다.
    """

    def __init__(self, source_api: ConfluenceAPI, target_api: ConfluenceAPI, db_session: Session):
        """
        PageValidator를 초기화합니다.

        :param source_api: 소스용 ConfluenceAPI 인스턴스.
        :param target_api: 타겟용 ConfluenceAPI 인스턴스.
        :param db_session: SQLAlchemy 세션 객체.
        """
        self.source_api = source_api
        self.target_api = target_api
        self.db = db_session
        # MigrationManager를 인스턴스화하여 헬퍼 메소드를 재사용할 수 있습니다.
        self.migrator = MigrationManager(source_api, target_api, db_session)

    def validate_tree(self, source_root_id: str, target_root_id: str) -> db.ValidationJob:
        """
        소스와 타겟 페이지 트리를 비교하고 불일치 항목을 기록합니다.

        :param source_root_id: 원본 콘텐츠의 루트 페이지 ID.
        :param target_root_id: 마이그레이션된 콘텐츠의 루트 페이지 ID.
        :return: 생성된 ValidationJob 객체.
        """
        log.info(f"소스 {source_root_id}와 타겟 {target_root_id} 간의 검증을 시작합니다.")
        
        # 1. ValidationJob 레코드 생성
        validation_job = db.ValidationJob(
            source_root_page_id=source_root_id,
            target_root_page_id=target_root_id,
            status='RUNNING'
        )
        self.db.add(validation_job)
        self.db.commit()
        self.db.refresh(validation_job)

        try:
            # 2. 두 페이지 트리 모두 가져오기
            source_pages = [self.source_api.get_page(source_root_id)] + self.source_api.get_all_descendants(source_root_id)
            target_pages = [self.target_api.get_page(target_root_id)] + self.target_api.get_all_descendants(target_root_id)

            source_titles = {page['title']: page for page in source_pages}
            target_titles = {page['title']: page for page in target_pages}

            # 3. 누락된 페이지 찾기
            missing_titles = source_titles.keys() - target_titles.keys()
            
            log.info(f"검증 결과 {len(missing_titles)}개의 누락된 페이지를 찾았습니다.")

            # 4. 결과 기록
            for title in missing_titles:
                missing_page = source_titles[title]
                result = db.ValidationResult(
                    validation_job_id=validation_job.id,
                    source_page_id=missing_page['id'],
                    source_page_title=missing_page['title'],
                    reason="타겟에서 페이지를 찾을 수 없음"
                )
                self.db.add(result)
            
            validation_job.missing_pages_count = len(missing_titles)
            validation_job.status = 'COMPLETED'
            self.db.commit()

        except Exception as e:
            log.error(f"검증 작업 {validation_job.id} 실패: {e}")
            validation_job.status = 'FAILED'
            self.db.commit()
            raise

        return validation_job

    def retry_failed_pages_for_job(self, job_id: int) -> dict:
        """
        특정 마이그레이션 작업에 대해 'FAILED'로 표시된 모든 페이지의 재마이그레이션을 시도합니다.

        :param job_id: 재시도할 MigrationJob의 ID.
        :return: 재시도 작업 요약을 담은 딕셔너리.
        """
        log.info(f"작업 {job_id}에서 실패한 페이지에 대한 재시도 프로세스를 시작합니다.")
        job = self.db.query(db.MigrationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"ID가 {job_id}인 작업을 찾을 수 없습니다.")

        failed_mappings = self.db.query(db.PageMapping).filter_by(job_id=job_id, status='FAILED').all()
        
        if not failed_mappings:
            log.info("재시도할 실패한 페이지가 없습니다.")
            return {"retried": 0, "success": 0, "failed": 0}

        retried_count = len(failed_mappings)
        success_count = 0
        
        target_space_key = self.target_api.get_space_key_from_page(job.target_root_page_id)

        for mapping in failed_mappings:
            try:
                log.info(f"페이지 재시도 중: '{mapping.source_page_title}' (소스 ID: {mapping.source_page_id})")
                
                # 소스에서 전체 페이지 데이터 가져오기
                source_page_data = self.source_api.get_page(mapping.source_page_id)
                if not source_page_data:
                    raise Exception("소스 페이지를 가져올 수 없습니다.")
                
                # 초기 마이그레이션과 동일한 로직을 사용하여 타겟 부모 ID 결정
                target_parent_id = self.migrator._get_target_parent_id(job, source_page_data)
                if not target_parent_id:
                    raise Exception("재시도 중 타겟 부모 ID를 결정할 수 없습니다.")

                # 페이지 생성 시도
                new_page = self.target_api.create_page(
                    space_key=target_space_key,
                    title=source_page_data['title'],
                    body=source_page_data['body']['storage']['value'],
                    parent_id=target_parent_id
                )
                
                # 성공 시 DB 업데이트
                mapping.target_page_id = new_page['id']
                mapping.target_parent_id = target_parent_id
                mapping.status = 'SUCCESS'
                mapping.error_message = None # 이전 오류 메시지 지우기
                job.successful_pages += 1
                job.failed_pages -= 1
                success_count += 1
                log.info(f"페이지 '{mapping.source_page_title}'를 성공적으로 재시도했습니다. 새 ID: {new_page['id']}")

            except Exception as e:
                error_msg = f"페이지 '{mapping.source_page_title}' 재시도 실패: {e}"
                log.error(error_msg)
                mapping.error_message = error_msg # 오류 메시지 업데이트
            
            self.db.commit()

        # 모든 실패가 해결되면 작업 상태 업데이트
        if job.failed_pages == 0:
            job.status = 'COMPLETED'
        
        self.db.commit()
        
        summary = {
            "retried": retried_count,
            "success": success_count,
            "failed": retried_count - success_count
        }
        log.info(f"작업 {job_id}에 대한 재시도 요약: {summary}")
        return summary

    def _find_target_parent_by_title(self, source_page: dict, target_space_key: str) -> str | None:
        """
        소스 페이지의 부모 제목을 사용하여 타겟에서 해당 부모 페이지를 찾습니다.
        이 메소드는 부모가 검증 루트 페이지가 아닌 경우에만 호출됩니다.
        """
        # 1. 소스 페이지의 직계 부모 ID와 제목을 찾습니다.
        if not source_page.get('ancestors'):
             # 이 경우는 remigrate_selected_pages에서 이미 처리되었어야 합니다.
            raise Exception("조상이 없는 페이지는 이 함수로 처리할 수 없습니다.")
        
        source_parent_id = source_page['ancestors'][-1]['id']
        source_parent_page = self.source_api.get_page(source_parent_id)
        if not source_parent_page:
            raise Exception(f"소스 부모 페이지 {source_parent_id}를 찾을 수 없습니다.")
        source_parent_title = source_parent_page['title']

        # 2. 타겟 스페이스 전체에서 해당 제목을 가진 페이지를 검색합니다.
        log.info(f"타겟 스페이스 '{target_space_key}'에서 부모 제목 '{source_parent_title}'(으)로 페이지를 검색합니다.")
        found_pages = self.target_api.search_pages_by_title(
            space_key=target_space_key,
            title=source_parent_title
        )

        # 3. 결과를 처리합니다.
        if len(found_pages) == 0:
            raise Exception(f"타겟에서 부모 페이지 '{source_parent_title}'를 찾을 수 없습니다.")
        if len(found_pages) > 1:
            # 여러 개가 발견되면 어떤 것이 진짜 부모인지 알 수 없으므로 오류 처리합니다.
            page_ids = [p['id'] for p in found_pages]
            raise Exception(f"타겟에서 중복된 부모 페이지 제목 '{source_parent_title}'이(가) 발견되었습니다. 후보 ID: {page_ids}")
            
        target_parent_id = found_pages[0]['id']
        log.info(f"타겟 부모 페이지를 찾았습니다: '{source_parent_title}' (ID: {target_parent_id})")
        return target_parent_id

    def remigrate_selected_pages(self, validation_job_id: int, source_page_ids: list[str]) -> dict:
        """
        검증 결과에서 누락된 것으로 확인된 페이지들을 제목 기반으로 부모를 찾아 재이관합니다.
        """
        log.info(f"검증 작업 #{validation_job_id}에서 선택된 {len(source_page_ids)}개 페이지의 재이관을 시작합니다.")
        validation_job = self.db.query(db.ValidationJob).get(validation_job_id)
        if not validation_job:
            raise ValueError(f"검증 작업 #{validation_job_id}을(를) 찾을 수 없습니다.")

        success_count = 0
        failed_count = 0
        
        try:
            target_space_key = self.target_api.get_space_key_from_page(validation_job.target_root_page_id)
        except Exception as e:
            log.error(f"타겟 스페이스 키를 가져올 수 없습니다: {e}")
            return {"total": len(source_page_ids), "success": 0, "failed": len(source_page_ids)}

        for page_id in source_page_ids:
            source_page_data = None
            try:
                source_page_data = self.source_api.get_page(page_id)
                if not source_page_data:
                    raise Exception("소스 페이지를 가져올 수 없습니다.")

                # 소스 페이지의 부모가 검증 루트인 특별한 경우를 처리합니다.
                direct_parent_id = source_page_data['ancestors'][-1]['id'] if source_page_data.get('ancestors') else None
                if direct_parent_id == validation_job.source_root_page_id:
                    target_parent_id = validation_job.target_root_page_id
                    log.info(f"소스 페이지의 부모가 검증 루트이므로, 타겟 부모를 {target_parent_id}로 설정합니다.")
                else:
                    target_parent_id = self._find_target_parent_by_title(
                        source_page=source_page_data,
                        target_space_key=target_space_key
                    )

                self.target_api.create_page(
                    space_key=target_space_key,
                    title=source_page_data['title'],
                    body=source_page_data['body']['storage']['value'],
                    parent_id=target_parent_id
                )
                success_count += 1
                log.info(f"페이지 '{source_page_data['title']}' (ID: {page_id})를 성공적으로 재이관했습니다.")
            
            except Exception as e:
                failed_count += 1
                page_title = source_page_data['title'] if source_page_data else f'ID {page_id}'
                log.error(f"페이지 '{page_title}' 재이관 실패: {e}")
        
        summary = {
            "total": len(source_page_ids),
            "success": success_count,
            "failed": failed_count
        }
        log.info(f"재이관 작업 요약: {summary}")
        return summary
