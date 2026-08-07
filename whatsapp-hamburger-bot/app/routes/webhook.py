from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.bot import ConversationBot

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/twilio")
async def twilio_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
):
    # Strip whatsapp: prefix from phone number
    phone = From.replace("whatsapp:", "").strip()
    message = Body.strip()

    bot = ConversationBot()
    response_text = bot.handle_message(phone=phone, message=message, db=db)

    # Escape XML special characters
    response_text = (
        response_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{response_text}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")
