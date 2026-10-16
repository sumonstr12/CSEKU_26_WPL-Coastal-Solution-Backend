
import os
import requests
from django.conf import settings


def send_otp_sms(phone_number: str, otp: str) -> bool:
    api_key = os.getenv("SMS_BD_API_KEY")

    if not api_key:
        raise RuntimeError("SMS_BD_API_KEY is not configured")

    phone = phone_number.strip().replace(" ", "")
				print(f"oto {otp}")

    if phone.startswith("+880"):
        phone = phone[1:]
    elif phone.startswith("880"):
        pass
    elif phone.startswith("01"):
        phone = "88" + phone
    else:
        raise ValueError("Invalid Bangladesh phone number")

    payload = {
        "api_key": api_key,
        "msg":  "Coastal Disaster Solution"
                f"Your verification code is {otp}. "
               "Do not share this code.",
        "to": phone,
    }

    response = requests.post(
        "https://api.sms.net.bd/sendsms",
        data=payload,
        timeout=15,
    )
    response.raise_for_status()

    result = response.json()

    # API reports error=0 for successful submission.
    return result.get("error") == 0