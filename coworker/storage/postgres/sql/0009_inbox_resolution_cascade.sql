ALTER TABLE agent.inbox_resolutions
DROP CONSTRAINT inbox_resolutions_user_id_inbox_item_id_fkey;

ALTER TABLE agent.inbox_resolutions
ADD CONSTRAINT inbox_resolutions_user_id_inbox_item_id_fkey
FOREIGN KEY (user_id, inbox_item_id)
REFERENCES agent.inbox_items(user_id, id)
ON DELETE CASCADE;
