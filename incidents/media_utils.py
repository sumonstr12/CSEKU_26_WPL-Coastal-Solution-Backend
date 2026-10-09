import io
import os
import subprocess
import tempfile

from PIL import Image


def compress_image(uploaded_file, max_width=1920, max_height=1920, quality=80):
    image = Image.open(uploaded_file)

    # Convert formats that don't work well with JPEG
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, "white")

        if image.mode == "P":
            image = image.convert("RGBA")

        if image.mode in ("RGBA", "LA"):
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")

    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Resize while maintaining aspect ratio
    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
    )

    output.seek(0)

    return output.read(), "image/jpeg", ".jpg"


def compress_video(uploaded_file, crf=28, preset="medium"):
    input_suffix = os.path.splitext(uploaded_file.name)[1] or ".mp4"

    input_file = tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix)
    output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")

    try:
        # Write uploaded video to temporary file
        for chunk in uploaded_file.chunks():
            input_file.write(chunk)

        input_file.close()
        output_file.close()

        command = [
            "ffmpeg",
            "-y",
            "-i",
            input_file.name,
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_file.name,
        ]

        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return output_file.name, "video/mp4"

    except subprocess.CalledProcessError as e:
        raise ValueError("Video compression failed.") from e

    finally:
        try:
            os.unlink(input_file.name)
        except FileNotFoundError:
            pass


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
}

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
}


def process_uploaded_file(uploaded_file):
    extension = os.path.splitext(uploaded_file.name)[1].lower()

    if extension in IMAGE_EXTENSIONS:
        data, content_type, new_extension = compress_image(uploaded_file)

        return {
            "data": data,
            "content_type": content_type,
            "extension": new_extension,
            "file_type": "photo",
        }

    elif extension in VIDEO_EXTENSIONS:
        path, content_type = compress_video(uploaded_file)

        with open(path, "rb") as f:
            data = f.read()

        os.unlink(path)

        return {
            "data": data,
            "content_type": content_type,
            "extension": ".mp4",
            "file_type": "video",
        }

    elif extension in AUDIO_EXTENSIONS:
        return {
            "data": uploaded_file.read(),
            "content_type": uploaded_file.content_type,
            "extension": extension,
            "file_type": "audio",
        }

    else:
        return {
            "data": uploaded_file.read(),
            "content_type": uploaded_file.content_type,
            "extension": extension,
            "file_type": "document",
        }