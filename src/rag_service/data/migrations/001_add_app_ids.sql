BEGIN;

-- ۱. افزودن ستون جدید
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS app_ids JSONB;

-- ۲. پر کردن از app_id موجود (idempotent)
UPDATE conversations
SET app_ids = to_jsonb(ARRAY[app_id])
WHERE app_ids IS NULL
  AND app_id IS NOT NULL
  AND app_id <> '';

-- ۳. app_id را nullable کنید (کلاینت جدید ممکن است فقط appIds بفرستد)
ALTER TABLE conversations
    ALTER COLUMN app_id DROP NOT NULL;

-- ۴. (اختیاری ولی توصیه‌شده) ایندکس GIN برای فیلتر contains
-- CREATE INDEX IF NOT EXISTS ix_conversations_app_ids
--     ON conversations USING GIN (app_ids);



-- ۱. حذف ایندکس قدیمی (اگر وجود دارد)
DROP INDEX IF EXISTS ix_conversations_user_tenant_app;

-- ۲. ساخت ایندکس B-tree جدید روی (tenant_id, user_id)
CREATE INDEX IF NOT EXISTS ix_conversations_tenant_user
    ON conversations (tenant_id, user_id);

-- ۳. ساخت ایندکس GIN روی app_ids
CREATE INDEX IF NOT EXISTS ix_conversations_app_ids
    ON conversations USING GIN (app_ids);

-- ۴. (اختیاری) ایندکس updated_at اگر ندارید
-- معمولاً قبلاً هست، ولی مطمئن شوید
CREATE INDEX IF NOT EXISTS ix_conversations_updated_at
    ON conversations (updated_at);

COMMIT;