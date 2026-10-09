import os
import uuid

from supabase import create_client


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "media")


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY
)


# ============================================================
# UPLOAD DJANGO FILE
# ============================================================

def upload_file(file, folder="uploads"):

    extension = os.path.splitext(file.name)[1]

    filename = f"{uuid.uuid4()}{extension}"

    file_path = f"{folder}/{filename}"

    file_content = file.read()

    supabase.storage.from_(SUPABASE_BUCKET).upload(
        file_path,
        file_content,
        {
            "content-type": file.content_type,
        }
    )

    public_url = (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{file_path}"
    )

    return {
        "path": file_path,
        "url": public_url,
        "filename": filename,
    }


# ============================================================
# UPLOAD BYTES
# ============================================================

def upload_bytes(data, file_path, content_type):
    """
    Upload processed/compressed bytes to Supabase.
    """

    supabase.storage.from_(SUPABASE_BUCKET).upload(
        file_path,
        data,
        {
            "content-type": content_type,
        }
    )

    public_url = (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{file_path}"
    )

    return {
        "path": file_path,
        "url": public_url,
    }