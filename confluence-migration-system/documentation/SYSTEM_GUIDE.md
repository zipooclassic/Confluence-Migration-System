# Confluence Migration System - User Guide

This guide provides a detailed walkthrough of the features of the Confluence Migration System.

## 1. Dashboard (대시보드)

The dashboard is the main landing page. It provides a summary of all migration jobs that have been run or are currently running.

-   **Job ID**: A unique identifier for each migration task.
-   **Source/Target Root ID**: The parent pages for the migration source and destination.
-   **Status**: The current state of the job:
    -   `PENDING`: The job has been created but has not started yet.
    -   `FETCHING`: The system is gathering the list of pages from the source Confluence.
    -   `RUNNING`: The migration is actively copying pages to the target.
    -   `COMPLETED`: The job finished successfully with no errors.
    -   `COMPLETED_WITH_ERRORS`: The job finished, but some pages failed to migrate.
    -   `FAILED`: The job encountered a critical error and could not be completed.
-   **Total Pages**: The total number of pages to be migrated in this job.
-   **Success/Failed**: A running count of successfully and unsuccessfully migrated pages.
-   **Actions**:
    -   `Details`: Click to view the page-by-page status for the job.

## 2. Creating a New Migration (새 마이그레이션 생성)

1.  From the dashboard, click the **"Create New Migration Job"** button.
2.  Fill in the form with the required details for both the **Source** and **Target** Confluence instances.
    -   **URL**: The base URL of the Confluence instance (e.g., `https://your-company.atlassian.net`).
    -   **Username**: The email address used to log in.
    -   **API Token**: An API token generated from your Atlassian account settings. **Do not use your password.**
    -   **Source Root Page ID**: The ID of the page you want to migrate *from*. All of its child pages will also be migrated.
    -   **Target Parent Page ID**: The ID of the page you want to migrate *to*. The migrated pages will be created as children of this page.
3.  Click the **"Start Migration"** button.
4.  You will be redirected to the dashboard. The new job will appear at the top of the list, and the migration will run in the background.

## 3. Viewing Job Details (작업 상세 정보 보기)

On the dashboard, click the **"Details"** button for any job to see a more granular view.

-   The top section provides a summary of the job and a progress bar.
-   The bottom section lists every single page in the job.
-   You can see the `source_id`, `title`, `status`, and the new `target_id` if successful.
-   If a page `FAILED`, the **Error** column will contain a message explaining why it failed.

### Retrying Failed Pages (실패한 페이지 재시도)

If a job has failed pages (`failed_pages > 0`), a **"Retry Failed Pages"** button will appear at the top of the Job Details page.
-   Clicking this button will start a new background task that attempts to migrate only the pages that previously failed.
-   The status of the pages will be updated in the table as they are retried.

## 4. Validating a Migration (마이그레이션 검증)

The validation tool helps you verify that all pages from the source tree exist in the target tree.

1.  Click the **"Validation"** tab in the navigation bar.
2.  Fill in the **Source Root Page ID** and **Target Root Page ID** you wish to compare. Note that the target root should be the parent page under which you migrated the content, which is the same ID you entered in the "Target Parent Page ID" field when creating the job.
3.  Provide credentials for both instances.
4.  Click **"Start Validation"**.
5.  The validation will run in the background. A new entry will appear in the "Past Validations" list.

### Viewing Validation Results (검증 결과 보기)

-   In the "Past Validations" list, click the **"View"** button.
-   The results page will show a summary and a list of any pages that were found in the source tree but not in the target tree (based on page title).
-   If the list is empty, it means the migration was successful at a structural level.
