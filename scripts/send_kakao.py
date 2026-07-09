"""
News.pic 카카오톡 알림 발송 스크립트

※ 이 파일은 GitHub Actions에서
   data 저장 + git push 성공 후에만 실행되어야 함
"""

import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import json
import requests
from datetime import datetime, timezone, timedelta


KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
NEWS_URL = "https://jinny0925.github.io/news-pic/"


def get_kakao_access_token(client_id, client_secret, refresh_token, sender_name=""):
    url = "https://kauth.kakao.com/oauth/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    response = requests.post(url, data=data, timeout=30)

    # 토큰 내용은 로그에 찍지 않음
    print(
       f"🔑 [{sender_name}]",
       response.status_code,
       response.text,
       flush=True
   )
   
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
            "web_url": NEWS_URL,
            "mobile_web_url": NEWS_URL
        },
        "button_title": "뉴스 보러가기"
    }

    data = {
        "receiver_uuids": json.dumps([friend_uuid]),
        "template_object": json.dumps(template, ensure_ascii=False)
    }

    response = requests.post(url, headers=headers, data=data, timeout=30)
    print(f"📩 [{sender_name}] 카카오 친구 메시지 결과:", response.status_code, response.text, flush=True)

    response.raise_for_status()


def send_both_messages():
    message_text = f"""🌅 오늘의 뉴스가 업데이트됐어요!

📅 {TODAY}
📰 오늘도 꼭 읽어보세요

{NEWS_URL}"""

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


def main():
    print("📨 카카오톡 알림 발송 시작", flush=True)
    send_both_messages()
    print("✅ 카카오톡 알림 발송 완료", flush=True)


if __name__ == "__main__":
    main()
