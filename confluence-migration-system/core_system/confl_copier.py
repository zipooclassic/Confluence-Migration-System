import logging
from atlassian import Confluence
from requests.exceptions import HTTPError

# 로깅 설정
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class ConfluenceAPI:
    """
    atlassian-python-api를 감싸서 Confluence 인스턴스와의 상호작용을 처리하는 래퍼 클래스.
    """

    def __init__(self, url, username, api_token):
        """
        Confluence API 클라이언트를 초기화합니다.

        :param url: Confluence 인스턴스의 URL.
        :param username: 인증에 사용할 사용자 이름.
        :param api_token: 인증에 사용할 API 토큰.
        """
        self.url = url
        try:
            self.confluence = Confluence(
                url=url,
                username=username,
                token=api_token
            )
            # 기본 정보를 가져와 연결 확인
            self.confluence.get_all_spaces(limit=1)
            log.info(f"{url}의 Confluence에 성공적으로 연결되었습니다.")
        except HTTPError as e:
            log.error(f"{url}의 Confluence에 연결하지 못했습니다. "
                      f"상태: {e.response.status_code}. 응답: {e.response.text}")
            raise ConnectionError(f"Confluence에 연결할 수 없습니다: {e.response.text}") from e
        except Exception as e:
            log.error(f"Confluence 초기화 중 예상치 못한 오류가 발생했습니다: {e}")
            raise

    def get_page(self, page_id):
        """
        ID로 단일 페이지를 가져옵니다.

        :param page_id: 가져올 페이지의 ID.
        :return: 페이지를 나타내는 딕셔너리, 찾지 못한 경우 None.
        """
        try:
            # content, version, ancestor 정보를 얻기 위해 expand 사용
            page = self.confluence.get_page_by_id(
                page_id,
                expand='body.storage,version,ancestors'
            )
            return page
        except HTTPError as e:
            if e.response.status_code == 404:
                log.warning(f"ID가 '{page_id}'인 페이지를 찾을 수 없습니다.")
                return None
            log.error(f"페이지 '{page_id}'를 가져오는 중 HTTPError 발생: {e}")
            raise
        except Exception as e:
            log.error(f"페이지 '{page_id}'를 가져오는 중 예상치 못한 오류 발생: {e}")
            raise

    def get_child_pages(self, parent_page_id):
        """
        주어진 상위 페이지의 모든 직계 하위 페이지를 가져옵니다.

        :param parent_page_id: 상위 페이지의 ID.
        :return: 하위 페이지 딕셔너리의 리스트.
        """
        try:
            # API가 제너레이터를 반환하므로 리스트로 변환
            return list(self.confluence.get_child_pages(parent_page_id))
        except HTTPError as e:
            log.error(f"페이지 '{parent_page_id}'의 하위 페이지를 가져오는 중 HTTPError 발생: {e}")
            raise
        except Exception as e:
            log.error(f"페이지 '{parent_page_id}'의 하위 페이지를 가져오는 중 예상치 못한 오류 발생: {e}")
            raise

    def get_all_descendants(self, root_page_id, max_depth=None):
        """
        루트 페이지의 모든 하위 페이지를 재귀적으로 가져옵니다.

        :param root_page_id: 시작할 페이지의 ID.
        :param max_depth: 탐색할 최대 깊이.
        :return: 모든 하위 페이지 딕셔너리의 플랫 리스트.
        """
        descendants = []
        pages_to_visit = [(root_page_id, 0)] # (page_id, depth)를 가진 스택
        
        while pages_to_visit:
            current_page_id, current_depth = pages_to_visit.pop(0)

            if max_depth is not None and current_depth >= max_depth:
                continue

            children = self.get_child_pages(current_page_id)
            if children:
                for child in children:
                    # 각 하위 페이지의 전체 상세 정보 가져오기
                    child_full = self.get_page(child['id'])
                    if child_full:
                        descendants.append(child_full)
                        pages_to_visit.append((child['id'], current_depth + 1))
        return descendants

    def create_page(self, space_key, title, body, parent_id=None):
        """
        타겟 Confluence 인스턴스에 새 페이지를 생성합니다.

        :param space_key: 페이지를 생성할 스페이스의 키.
        :param title: 새 페이지의 제목.
        :param body: 페이지의 HTML 콘텐츠 ('storage' 형식).
        :param parent_id: 상위 페이지의 ID (선택 사항).
        :return: 생성된 페이지 객체 딕셔너리.
        """
        try:
            page = self.confluence.create_page(
                space=space_key,
                title=title,
                body=body,
                parent_id=parent_id,
                representation='storage' # 완전한 HTML 충실도를 위해 storage 형식 사용
            )
            log.info(f"페이지 '{title}'이(가) 새 ID {page['id']}로 성공적으로 생성되었습니다.")
            return page
        except HTTPError as e:
            log.error(f"페이지 '{title}' 생성 중 HTTPError 발생: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            log.error(f"페이지 '{title}' 생성 중 예상치 못한 오류 발생: {e}")
            raise

    def get_space_key_from_page(self, page_id):
        """
        주어진 페이지의 스페이스 키를 찾는 헬퍼 함수.
        create_page는 상위 ID뿐만 아니라 스페이스 키가 필요하기 때문에 이 함수가 필요합니다.

        :param page_id: 원하는 스페이스 내 페이지의 ID.
        :return: 스페이스 키 문자열.
        """
        try:
            page = self.get_page(page_id)
            if page and 'space' in page and 'key' in page['space']:
                return page['space']['key']
            # 이전 API 버전이나 다른 구조를 위한 폴백
            if 'ancestors' in page and page['ancestors']:
                 # 첫 번째 조상은 보통 스페이스 홈
                 space_info = page['ancestors'][0].get('space')
                 if space_info:
                     return space_info['key']
            # 페이지에 조상이 없다면 루트 페이지일 수 있음
            page_info = self.confluence.get_page_by_id(page_id, expand="space")
            return page_info['space']['key']
        except Exception as e:
            log.error(f"페이지 ID {page_id}의 스페이스 키를 확인할 수 없습니다: {e}")
            raise

    def search_pages_by_title(self, space_key: str, title: str, ancestor_id: str | None = None) -> list:
        """
        주어진 제목과 상위 페이지 ID를 기준으로 페이지를 검색합니다.

        :param space_key: 검색할 스페이스 키.
        :param title: 검색할 페이지의 정확한 제목.
        :param ancestor_id: 검색 범위를 제한할 상위 페이지 ID (선택 사항).
        :return: 검색된 페이지 딕셔너리의 리스트.
        """
        # 제목에 포함된 따옴표는 CQL에서 문제를 일으키므로 이스케이프 처리합니다.
        sanitized_title = title.replace('"', '\\"')
        cql = f'space = "{space_key}" and title = "{sanitized_title}"'
        if ancestor_id:
            cql += f' and ancestor = {ancestor_id}'
        
        try:
            results = self.confluence.cql(cql, limit=10) # 중복 제목을 고려하여 limit을 넉넉하게 설정
            return results.get('results', [])
        except HTTPError as e:
            log.error(f"CQL 검색 실패 ('{cql}'): {e.response.text}")
            raise
        except Exception as e:
            log.error(f"CQL 검색 중 예상치 못한 오류 발생 ('{cql}'): {e}")
            raise


# 예제 사용법 (테스트 목적)
if __name__ == '__main__':
    # 이 블록은 스크립트가 직접 실행될 때만 실행됩니다
    # 환경 변수 설정이 필요합니다.
    import os
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='../.env')

    SOURCE_URL = os.getenv("SOURCE_CONFLUENCE_URL")
    SOURCE_USER = os.getenv("SOURCE_CONFLUENCE_USERNAME")
    SOURCE_TOKEN = os.getenv("SOURCE_CONFLUENCE_API_TOKEN")
    
    if not all([SOURCE_URL, SOURCE_USER, SOURCE_TOKEN]):
        print("이 예제를 실행하려면 .env 파일에 SOURCE Confluence 환경 변수를 설정하세요.")
    else:
        try:
            # 소스 Confluence API 초기화
            source_confluence = ConfluenceAPI(SOURCE_URL, SOURCE_USER, SOURCE_TOKEN)
            
            # --- get_page 테스트 ---
            # 소스 Confluence의 실제 페이지 ID로 교체하세요
            test_page_id = "12345678" # 중요: 이 값을 변경하세요
            print(f"--- get_page({test_page_id}) 테스트 ---")
            page = source_confluence.get_page(test_page_id)
            if page:
                print(f"찾은 페이지: {page['title']}")
                print(f"  ID: {page['id']}")
                print(f"  상위 ID: {page.get('parent', {}).get('id')}")
            else:
                print(f"ID가 {test_page_id}인 페이지를 찾을 수 없습니다.")

            # --- get_all_descendants 테스트 ---
            print(f"\n--- get_all_descendants({test_page_id}) 테스트 ---")
            descendants = source_confluence.get_all_descendants(test_page_id)
            print(f"{len(descendants)}개의 하위 페이지를 찾았습니다.")
            for desc in descendants:
                print(f"  - {desc['title']} (ID: {desc['id']})")

        except ConnectionError as e:
            print(f"연결 실패: {e}")
        except Exception as e:
            print(f"오류 발생: {e}")
