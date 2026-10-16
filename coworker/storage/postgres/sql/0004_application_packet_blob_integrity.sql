ALTER TABLE blob.objects
    ADD CONSTRAINT blob_objects_user_id_id_key
    UNIQUE (user_id, id);

ALTER TABLE career.application_packets
    ADD COLUMN blob_id UUID;

UPDATE career.application_packets
SET blob_id = (data->>'blob_id')::uuid
WHERE blob_id IS NULL
  AND data ? 'blob_id';

ALTER TABLE career.application_packets
    ADD CONSTRAINT application_packets_user_blob_fkey
        FOREIGN KEY (user_id, blob_id)
        REFERENCES blob.objects(user_id, id);
