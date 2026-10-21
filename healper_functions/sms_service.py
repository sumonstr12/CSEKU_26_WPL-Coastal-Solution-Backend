
import os
import requests


def send_otp_sms(phone_number: str, otp: str) -> bool:
    api_key = os.getenv("SMS_BD_API_KEY")

    if not api_key:
        raise RuntimeError("SMS_BD_API_KEY is not configured")

    phone = phone_number.strip().replace(" ", "")

    print(f"OTP for verification: {otp}", flush=True)

    # Normalize Bangladesh phone number
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
        "msg": (
            "Coastal Disaster Solution: "
            f"Your verification code is {otp}. "
            "Do not share this code."
        ),
        "to": phone,
    }

    try:
        response = requests.post(
            "https://api.sms.net.bd/sendsms",
            data=payload,
            timeout=15,
        )

        response.raise_for_status()
        result = response.json()

        # SMS provider reports error=0 on successful submission
        if result.get("error") == 0:
            print("OTP SMS submitted successfully", flush=True)
            return True

        print(
            f"SMS provider returned an error: {result.get('error')}",
            flush=True,
        )
        return False

    except requests.RequestException as exc:
        print(f"Failed to send OTP SMS: {exc}", flush=True)
        raise
