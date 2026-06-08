import os
import mimetypes
from aiogram.types import Message


class MediaService:
    """
    Service to handle and process various media types from Telegram messages.
    Converts media inputs (photos, voices, documents, audio, videos) into formats compatible with Gemini.
    """

    @staticmethod
    def is_text_file(filename: str, mime_type: str) -> bool:
        """
        Check if the file is a text or code file that can be read as a string.
        """
        text_extensions = {
            ".py",
            ".txt",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".conf",
            ".md",
            ".csv",
            ".sh",
            ".bat",
            ".js",
            ".ts",
            ".css",
            ".html",
            ".htm",
            ".sql",
            ".rs",
            ".go",
            ".c",
            ".cpp",
            ".h",
            ".java",
            ".kt",
            ".swift",
            ".rb",
        }
        ext = os.path.splitext(filename.lower())[1]
        if ext in text_extensions:
            return True
        if mime_type and (
            mime_type.startswith("text/")
            or mime_type
            in ["application/json", "application/xml", "application/x-javascript"]
        ):
            return True
        return False

    @classmethod
    async def process_message_media(
        cls, message: Message, override_text: str = None
    ) -> tuple[str, list[dict]]:
        """
        Processes message media (photos, voice, documents, audio, video) and returns:
        - Updated text/prompt (with text file contents appended if applicable)
        - List of media parts for Gemini: [{"data": bytes, "mime_type": str}]
        """
        text = (
            override_text
            if override_text is not None
            else (message.text or message.caption or "")
        )
        media_parts = []

        # 1. Voice Messages
        if message.voice:
            voice = message.voice
            file_info = await message.bot.get_file(voice.file_id)
            file = await message.bot.download_file(file_info.file_path)
            voice_bytes = file.read()
            mime_type = voice.mime_type or "audio/ogg"
            media_parts.append({"data": voice_bytes, "mime_type": mime_type})

        # 2. Photos (Single photo - media groups are processed separately)
        elif message.photo and not message.media_group_id:
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            file = await message.bot.download_file(file_info.file_path)
            photo_bytes = file.read()
            media_parts.append({"data": photo_bytes, "mime_type": "image/jpeg"})

        # 3. Audio files
        elif message.audio:
            audio = message.audio
            file_info = await message.bot.get_file(audio.file_id)
            file = await message.bot.download_file(file_info.file_path)
            audio_bytes = file.read()
            mime_type = audio.mime_type or "audio/mpeg"
            media_parts.append({"data": audio_bytes, "mime_type": mime_type})

        # 4. Videos / Video notes
        elif message.video:
            video = message.video
            file_info = await message.bot.get_file(video.file_id)
            file = await message.bot.download_file(file_info.file_path)
            video_bytes = file.read()
            mime_type = video.mime_type or "video/mp4"
            media_parts.append({"data": video_bytes, "mime_type": mime_type})
        elif message.video_note:
            video_note = message.video_note
            file_info = await message.bot.get_file(video_note.file_id)
            file = await message.bot.download_file(file_info.file_path)
            video_bytes = file.read()
            media_parts.append({"data": video_bytes, "mime_type": "video/mp4"})

        # 5. Documents / General Files
        elif message.document:
            doc = message.document
            file_info = await message.bot.get_file(doc.file_id)
            file = await message.bot.download_file(file_info.file_path)
            file_bytes = file.read()

            filename = doc.file_name or "file"
            mime_type = (
                doc.mime_type
                or mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )

            # Check if it's a text file we can read directly
            if cls.is_text_file(filename, mime_type):
                try:
                    text_content = file_bytes.decode("utf-8")
                    # Format text content and append to prompt
                    file_prompt = (
                        f"\n\n[Attached File: {filename}]\n```\n{text_content}\n```"
                    )
                    text += file_prompt
                except UnicodeDecodeError:
                    # Fallback to sending as byte part if UTF-8 decode fails
                    media_parts.append({"data": file_bytes, "mime_type": "text/plain"})
            else:
                # PDF, image, audio, etc. passed as raw bytes
                media_parts.append({"data": file_bytes, "mime_type": mime_type})

        return text.strip(), media_parts
