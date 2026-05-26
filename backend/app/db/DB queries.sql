select * from dicom_metadata_logs order by created_at DESC LIMIT 20;

select * from thumbnails order by created_at DESC LIMIT 20;

select * from event_logs order by TIMESTAMP DESC  LIMIT 10;

select * from uid_path_mapping order by created_at DESC LIMIT 20;

select * from conversion_logs order by TIMESTAMP DESC  LIMIT 10;

select * from alembic_version;

SELECT study_uid, series_uid, sop_uid, created_at
FROM dicom_metadata_logs
WHERE study_uid = 'YOUR_STUDY_UID'
ORDER BY created_at DESC
LIMIT 5;


ROLLBACK;
