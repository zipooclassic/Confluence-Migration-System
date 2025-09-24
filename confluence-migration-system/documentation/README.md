# Confluence Migration System

A web-based management system for bulk migrating Atlassian Confluence pages from a source system to a target system.

## Features (주요 기능)

-   **Tree-based Migration**: Migrates a parent page and all its descendants, preserving the hierarchy.
-   **Dashboard**: Monitor the progress of migration jobs in real-time.
-   **Error Handling & Retry**: Failed pages are logged and can be retried individually.
-   **Validation**: Compare the page structure between the source and target to verify the migration.

## Setup & Installation (설치 및 설정)

### 1. Clone the Repository (저장소 복제)
```bash
git clone <repository-url>
cd confluence-migration-system
```

### 2. Create a Virtual Environment (가상 환경 생성)
It is highly recommended to use a virtual environment.
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

### 3. Install Dependencies (의존성 설치)
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (환경 변수 설정)
Copy the example `.env.example` file to a new `.env` file.
```bash
cp .env.example .env
```
Now, edit the `.env` file with your specific Confluence details:
```ini
# Confluence Source System
SOURCE_CONFLUENCE_URL=https://your-source.atlassian.net
SOURCE_CONFLUENCE_USERNAME=your-email@example.com
SOURCE_CONFLUENCE_API_TOKEN=your_source_api_token

# Confluence Target System
TARGET_CONFLUENCE_URL=https://your-target.atlassian.net
TARGET_CONFLUENCE_USERNAME=your-email@example.com
TARGET_CONFLUENCE_API_TOKEN=your_target_api_token

# Flask
SECRET_KEY=a_very_secret_key_that_should_be_changed
```

## How to Run (실행 방법)

Once the setup is complete, you can run the web application with the following command:

```bash
python main.py
```

The application will be available at `http://0.0.0.0:5001`. Open this URL in your web browser to access the dashboard.
