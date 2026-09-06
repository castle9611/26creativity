@echo off
rem Copy this file to nextcloud_config.bat and fill in the intranet values.
rem Use a dedicated Nextcloud app password, not the user's login password.
set "NEXTCLOUD_ENABLED=1"
set "NEXTCLOUD_URL=http://nextcloud.internal"
set "NEXTCLOUD_USERNAME=oa_service"
set "NEXTCLOUD_APP_PASSWORD=replace-with-app-password"
set "NEXTCLOUD_ROOT_PATH=OA"
set "NEXTCLOUD_VERIFY_SSL=1"

rem Existing direct ONLYOFFICE integration can remain enabled for legacy OA documents.
rem New cloud documents are opened by the ONLYOFFICE app installed in Nextcloud.
set "ONLYOFFICE_ENABLED=1"
set "ONLYOFFICE_SERVER_URL=http://onlyoffice.internal"
set "ONLYOFFICE_JWT_ENABLED=1"
set "ONLYOFFICE_JWT_SECRET=replace-with-onlyoffice-jwt-secret"
set "APP_PUBLIC_URL=http://oa.internal:5000"
