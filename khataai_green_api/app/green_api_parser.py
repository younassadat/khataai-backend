"""
KhataAI — Green API webhook payload parser
Owner: Younas

Green API sends a completely different webhook format than Meta.
This file handles parsing Green API payloads into the same
internal format our handlers expect.

Green API webhook format:
{
    "typeWebhook": "incomingMessageReceived",
    "instanceData": {...},
    "timestamp": 1234567890,
    "idMessage": "...",
    "senderData": {
        "chatId": "923001234567@c.us",
        "chatName": "Seller Name",
        "sender": "923001234567@c.us",
        "senderName": "Seller Name"
    },
    "messageData": {
        "typeMessage": "textMessage",
        "textMessageData": {"textMessage": "Hello"},
        # OR for images:
        "typeMessage": "imageMessage",
        "fileMessageData": {
            "downloadUrl": "https://...",
            "caption": "udhaar"
        },
        # OR for audio:
        "typeMessage": "audioMessage",
        "fileMessageData": {
            "downloadUrl": "https://..."
        }
    }
}
"""


def extract_message_green_api(payload: dict):
    """
    Parses a Green API webhook payload and returns:
        (message, phone_number)

    where message is normalised to match what our handlers expect:
        {
            "type": "text" | "image" | "audio",
            "text": {"body": "..."},          # for text
            "image": {"id": "...", "caption": "..."},  # for image (id = downloadUrl)
            "audio": {"id": "..."},           # for audio (id = downloadUrl)
        }

    Returns (None, None) for non-message webhooks (status updates etc.)
    """
    # Only process incoming messages
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return None, None

    sender_data = payload.get("senderData", {})
    message_data = payload.get("messageData", {})

    # Extract phone number — strip @c.us suffix
    chat_id = sender_data.get("chatId", "")
    if not chat_id:
        return None, None

    phone_number = "+" + chat_id.replace("@c.us", "").replace("@g.us", "")

    # Skip group messages — we only handle individual chats
    if "@g.us" in chat_id:
        return None, None

    type_message = message_data.get("typeMessage", "")

    # Text message
    if type_message == "textMessage":
        text = message_data.get("textMessageData", {}).get("textMessage", "")
        message = {
            "type": "text",
            "text": {"body": text},
        }
        return message, phone_number

    # Image message
    if type_message == "imageMessage":
        file_data = message_data.get("fileMessageData", {})
        download_url = file_data.get("downloadUrl", "")
        caption = file_data.get("caption", "")
        message = {
            "type": "image",
            "image": {
                "id": download_url,   # We use download URL directly as "id"
                "caption": caption,
            },
        }
        return message, phone_number

    # Audio / voice note message
    if type_message in ("audioMessage", "voiceMessage", "pttMessage"):
        file_data = message_data.get("fileMessageData", {})
        download_url = file_data.get("downloadUrl", "")
        message = {
            "type": "audio",
            "audio": {
                "id": download_url,   # We use download URL directly as "id"
            },
        }
        return message, phone_number

    # Document (PDF invoice etc.) — treat as image for OCR
    if type_message == "documentMessage":
        file_data = message_data.get("fileMessageData", {})
        download_url = file_data.get("downloadUrl", "")
        caption = file_data.get("caption", "")
        message = {
            "type": "image",
            "image": {
                "id": download_url,
                "caption": caption,
            },
        }
        return message, phone_number

    # Unknown type — return unknown so fallback message fires
    message = {"type": "unknown"}
    return message, phone_number
