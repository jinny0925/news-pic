import os
import json
import requests
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def get_kakao_access_token(client_id, client_secret, refresh_token, sender_name=""):
    url = "https://kauth.kakao.com/oauth/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    response = requests.post(url, data=data, timeout=30)
    print(f"🔑 [{sender_name}] 토큰 갱신:", response.status_code, response.text)
    response.raise_for_status()

    return response.json()["access_token"]


def send_kakao_friend_message(text, client_id, client_secret, refresh_token, friend_uuid, sender_name=""):
    access_token = get_kakao_access_token(client_id, client_secret, refresh_token, sender_name)

    url = "https://kapi.kakao.com/v1/api/talk/friends/message/default/send"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    template = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": "https://jinny0925.github.io",
            "mobile_web_url": "https://jinny0925.github.io"
        },
        "button_title": "페이지 보기"
    }

    data = {
        "receiver_uuids": json.dumps([friend_uuid]),
        "template_object": json.dumps(template, ensure_ascii=False)
    }

    response = requests.post(url, headers=headers, data=data, timeout=30)
    print(f"📩 [{sender_name}] 메시지 발송:", response.status_code, response.text)
    response.raise_for_status()


def main():
    message_text = f"✅ 카카오톡 발송 테스트입니다.\n\n시간: {TODAY}\n뉴스봇 연결 확인용 메시지예요."

    print("📨 카카오톡 발송 테스트 시작")

    send_kakao_friend_message(
        text=message_text,
        client_id=os.environ["KAKAO_CLIENT_ID_WIFE"],
        client_secret=os.environ["KAKAO_CLIENT_SECRET_WIFE"],
        refresh_token=os.environ["KAKAO_REFRESH_TOKEN_WIFE"],
        friend_uuid=os.environ["KAKAO_FRIEND_UUID_HUSBAND"],
        sender_name="아내→남편",
    )

    send_kakao_friend_message(
        text=message_text,
        client_id=os.environ["KAKAO_CLIENT_ID_HUSBAND"],
        client_secret=os.environ["KAKAO_CLIENT_SECRET_HUSBAND"],
        refresh_token=os.environ["KAKAO_REFRESH_TOKEN_HUSBAND"],
        friend_uuid=os.environ["KAKAO_FRIEND_UUID_WIFE"],
        sender_name="남편→아내",
    )

    print("✅ 카카오톡 발송 테스트 완료")


if __name__ == "__main__":
    main()
