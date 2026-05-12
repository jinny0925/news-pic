"""
News.pic 일일 생성 스크립트 (v6: Gemini 재시도 + 카카오 양방향 메시지)

필요한 환경변수 (GitHub Secrets):
  공통:
    NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY

  아내 → 남편 발송용:
    KAKAO_CLIENT_ID_WIFE
    KAKAO_CLIENT_SECRET_WIFE
    KAKAO_REFRESH_TOKEN_WIFE
    KAKAO_FRIEND_UUID_HUSBAND

  남편 → 아내 발송용:
    KAKAO_CLIENT_ID_HUSBAND
    KAKAO_CLIENT_SECRET_HUSBAND
    KAKAO_REFRESH_TOKEN_HUSBAND
    KAKAO_FRIEND_UUID_WIFE
"""

import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import json
import urllib.parse
import requests
import time
import shutil
from datetime import datetime, timezone, timedelta

import google.generativeai as genai


# ===== 환경변수 =====
NAVER_CLIENT_ID = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
NAVER_CLIENT_SECRET = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()

KST = timezone(timedelta(hours=9))
TODAY = "2026-05-12"


# ===== 카카오 메시지 =====
def get_kakao_access_token(client_id, client_secret, refresh_token, sender_name=""):
    url = "https://kauth.kakao.com/oauth/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    response = requests.post(url, data=data, timeout=30)
    print(f"🔑 [{sender_name}] 카카오 토큰 갱신 결과:", response.status_code, response.text, flush=True)
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
    print(f"📩 [{sender_name}] 카카오 친구 메시지 결과:", response.status_code, response.text, flush=True)
    response.raise_for_status()


def send_both_messages():
    message_text = f"🌅 오늘의 뉴스가 업데이트됐어요!\n\n📅 {TODAY}\n📰 오늘도 꼭 읽어보세요"

    try:
        send_kakao_friend_message(
            text=message_text,
            client_id=os.environ["KAKAO_CLIENT_ID_WIFE"],
            client_secret=os.environ["KAKAO_CLIENT_SECRET_WIFE"],
            refresh_token=os.environ["KAKAO_REFRESH_TOKEN_WIFE"],
            friend_uuid=os.environ["KAKAO_FRIEND_UUID_HUSBAND"],
            sender_name="아내→남편",
        )
    except Exception as e:
        print(f"⚠️ 아내 → 남편 메시지 전송 실패 (무시하고 진행): {e}", flush=True)

    try:
        send_kakao_friend_message(
            text=message_text,
            client_id=os.environ["KAKAO_CLIENT_ID_HUSBAND"],
            client_secret=os.environ["KAKAO_CLIENT_SECRET_HUSBAND"],
            refresh_token=os.environ["KAKAO_REFRESH_TOKEN_HUSBAND"],
            friend_uuid=os.environ["KAKAO_FRIEND_UUID_WIFE"],
            sender_name="남편→아내",
        )
    except Exception as e:
        print(f"⚠️ 남편 → 아내 메시지 전송 실패 (무시하고 진행): {e}", flush=True)


# ===== 1. 네이버 뉴스 수집 =====
def fetch_news():
    categories = ["정치", "경제", "IT", "사회", "세계", "문화", "라이프"]
    all_news = []

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    for cat in categories:
        url = (
            "https://openapi.naver.com/v1/search/news.json"
            f"?query={urllib.parse.quote(cat)}&display=20&sort=date"
        )

        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()

            items = r.json().get("items", [])

            for item in items:
                title = (
                    item.get("title", "")
                    .replace("<b>", "")
                    .replace("</b>", "")
                    .replace("&quot;", '"')
                    .replace("&amp;", "&")
                )

                desc = (
                    item.get("description", "")
                    .replace("<b>", "")
                    .replace("</b>", "")
                    .replace("&quot;", '"')
                    .replace("&amp;", "&")
                )

                all_news.append({
                    "category_hint": cat,
                    "title": title,
                    "description": desc,
                    "link": item.get("link", ""),
                    "pubDate": item.get("pubDate", "")
                })

        except Exception as e:
            print(f"⚠️ {cat} 카테고리 수집 실패: {e}", flush=True)
            continue

    print(f"✅ 총 {len(all_news)}개 뉴스 수집", flush=True)
    return all_news


# ===== 2. Gemini 큐레이션 =====
def extract_json_from_text(text):
    text = text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def load_latest_as_fallback():
    try:
        if os.path.exists("data/latest.json"):
            with open("data/latest.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            print("⚠️ Gemini 실패로 기존 latest.json 백업 사용", flush=True)
            return data

    except Exception as e:
        print(f"⚠️ latest.json 백업 로드 실패: {e}", flush=True)

    return {"cards": []}


def curate_with_gemini(news_list):
    print("🤖 Gemini API 호출 시작...", flush=True)

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    news_text = "\n\n".join([
        f"[{i}] ({n['category_hint']}) {n['title']}\n"
        f"설명: {(n.get('description') or '')[:180]}\n"
        f"링크: {n.get('link')}"
        for i, n in enumerate(news_list[:140])
    ])

    prompt = f"""당신은 뉴스 큐레이터입니다. 아래 뉴스 목록 중 오늘의 인포그래픽 카드로 만들 뉴스를 선별하세요.

선별 기준:
1. 다음 5개 카테고리에서 각 2~3개씩 선별 (총 12~15개):
   - world (국제): 국제 정치, 외교, 세계 이슈
   - economy (경제): 주식, 부동산, 산업, 금융
   - tech (기술): IT, AI, 과학기술, 신제품
   - society (사회): 정치, 사회 이슈, 정책
   - life (라이프): 문화, 트렌드, 일상

2. 그중 가장 중요한 1개를 "is_headline": true 로 표시하세요.
3. 인포그래픽으로 표현 가능한 뉴스 위주로 고르세요.
4. 다음은 제외하세요:
   - 사망/사고/범죄 관련 뉴스
   - 운세/별자리/연예 가십
   - 광고성 보도
   - 차별/혐오 가능성 있는 내용

반드시 아래 JSON 형식만 반환하세요. 설명 문장, 코드펜스 없이 JSON만 반환하세요.

{{
  "cards": [
    {{
      "id": "world-example",
      "is_headline": false,
      "category": "world",
      "category_label": "🌍 국제",
      "viz_type": "timeline",
      "title": "카드 제목",
      "subtitle": "한 줄 설명",
      "viz_data": {{
        "stats": [
          {{"value": "3일", "label": "기간"}},
          {{"value": "2국", "label": "참여"}},
          {{"value": "1170+", "label": "개전 일"}}
        ],
        "main_number": "+47%",
        "main_text": "주요 수치 한 줄 설명"
      }},
      "image_prompt": "cute pastel infographic illustration, no text",
      "detail": {{
        "summary": "한 줄 요약",
        "points": ["핵심 포인트 1", "핵심 포인트 2", "핵심 포인트 3", "핵심 포인트 4"],
        "quote": "의미있는 한 마디",
        "context": "왜 중요한지 배경",
        "source_url": "원문 링크"
      }}
    }}
  ]
}}

중요:
- 총 12~15개
- is_headline=true는 정확히 1개
- category는 world/economy/tech/society/life 중 하나
- category_label은 🌍 국제 / 💰 경제 / 💻 기술 / 🏛 사회 / 🌱 라이프 중 하나
- JSON만 반환

뉴스 목록:
{news_text}
"""

    last_error = None

    for attempt in range(1, 4):
        try:
            print(f"🤖 Gemini 시도 {attempt}/3", flush=True)

            response = model.generate_content(
                prompt,
                request_options={"timeout": 600}
            )

            text = response.text.strip()
            data = extract_json_from_text(text)
            cards = data.get("cards", [])

            if not cards:
                raise ValueError("Gemini 응답에 cards가 없습니다.")

            cat_counts = {}
            headline_count = 0

            for c in cards:
                cat = c.get("category", "unknown")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

                if c.get("is_headline"):
                    headline_count += 1

            print(f"✅ Gemini가 총 {len(cards)}개 카드 생성", flush=True)
            print(f"   카테고리별: {cat_counts}", flush=True)
            print(f"   헤드라인: {headline_count}개", flush=True)

            return data

        except Exception as e:
            last_error = e
            print(f"⚠️ Gemini 시도 {attempt}/3 실패: {e}", flush=True)

            if attempt < 3:
                wait_time = 20 * attempt
                print(f"⏳ {wait_time}초 후 재시도", flush=True)
                time.sleep(wait_time)

    print(f"❌ Gemini 큐레이션 최종 실패: {last_error}", flush=True)
    return load_latest_as_fallback()


# ===== 3. 이미지 다운로드 =====
def download_image(url, save_path, max_retries=2):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=60, stream=True)

            if r.status_code == 429:
                wait_time = 30 * (attempt + 1)
                print(f"      ⏳ 429 Too Many Requests, {wait_time}초 대기...", flush=True)
                time.sleep(wait_time)
                continue

            r.raise_for_status()

            content_type = r.headers.get("content-type", "")
            if "image" not in content_type:
                print(f"      ⚠️ 이미지가 아님 ({content_type})", flush=True)
                time.sleep(5)
                continue

            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = os.path.getsize(save_path)

            if file_size < 1000:
                print(f"      ⚠️ 파일 너무 작음 ({file_size}B)", flush=True)
                os.remove(save_path)
                time.sleep(5)
                continue

            return True

        except requests.Timeout:
            print(f"      ⚠️ 시도 {attempt + 1}/{max_retries} timeout", flush=True)
            time.sleep(10)

        except Exception as e:
            print(f"      ⚠️ 시도 {attempt + 1}/{max_retries} 실패: {e}", flush=True)
            time.sleep(10)

    return False


def generate_and_save_images(curated_data):
    image_dir = f"data/images/{TODAY}"
    os.makedirs(image_dir, exist_ok=True)

    cards = curated_data.get("cards", [])
    success_count = 0
    start_time = time.time()

    for idx, card in enumerate(cards):
        card_id = card.get("id", f"card-{idx}")
        prompt = card.get("image_prompt", "cute pastel infographic")

        full_prompt = (
            f"{prompt}, cute hand-drawn infographic style, pastel colors, "
            "cream background, soft shadows, rounded shapes, no text, no words, "
            "editorial illustration"
        )

        encoded = urllib.parse.quote(full_prompt)
        seed = abs(hash(card_id)) % 100000

        pollinations_url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=800&height=500&seed={seed}&nologo=true"
        )

        filename = f"{card_id}.jpg"
        save_path = f"{image_dir}/{filename}"
        github_path = f"data/images/{TODAY}/{filename}"

        elapsed = int(time.time() - start_time)
        print(f"🎨 [{idx + 1}/{len(cards)}] {card_id} ({elapsed}s 경과)", flush=True)

        if download_image(pollinations_url, save_path):
            card["image_url"] = github_path
            success_count += 1
            print("      ✅ 저장됨", flush=True)
        else:
            card["image_url"] = pollinations_url
            print("      ⚠️ 다운로드 실패, 백업 URL 사용", flush=True)

        if idx < len(cards) - 1:
            time.sleep(10)

    print(f"\n📊 이미지 다운로드: {success_count}/{len(cards)} 성공", flush=True)
    return curated_data


# ===== 4. 오래된 이미지 정리 =====
def cleanup_old_images(days_to_keep=30):
    images_root = "data/images"

    if not os.path.exists(images_root):
        return

    cutoff_date = datetime.now(KST) - timedelta(days=days_to_keep)
    deleted_count = 0

    for folder_name in os.listdir(images_root):
        folder_path = os.path.join(images_root, folder_name)

        if not os.path.isdir(folder_path):
            continue

        try:
            folder_date = datetime.strptime(folder_name, "%Y-%m-%d").replace(tzinfo=KST)

            if folder_date < cutoff_date:
                shutil.rmtree(folder_path)
                deleted_count += 1
                print(f"🗑️ 오래된 이미지 삭제: {folder_name}", flush=True)

        except ValueError:
            continue

    if deleted_count > 0:
        print(f"✅ 총 {deleted_count}개 오래된 폴더 삭제", flush=True)


# ===== 5. 저장 =====
def save_data(data):
    data["date"] = TODAY
    data["generated_at"] = datetime.now(KST).isoformat()

    os.makedirs("data", exist_ok=True)

    daily_path = f"data/{TODAY}.json"

    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ 저장됨: {daily_path}", flush=True)

    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ latest.json 업데이트", flush=True)


# ===== 메인 =====
def main():
    print(f"🌅 {TODAY} 뉴스 생성 시작", flush=True)
    print(f"⏰ 시작 시간: {datetime.now(KST).strftime('%H:%M:%S')}", flush=True)

    if not all([NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY]):
        print("❌ 환경변수가 설정되지 않았어요!", flush=True)
        return

    print("\n[1/5] 📰 뉴스 수집", flush=True)
    news = fetch_news()

    if not news:
        print("❌ 뉴스를 가져오지 못했어요", flush=True)
        return

    print("\n[2/5] 🤖 AI 큐레이션", flush=True)
    curated = curate_with_gemini(news)

    if not curated.get("cards"):
        print("❌ 큐레이션 실패 및 백업 데이터 없음", flush=True)
        return

    print("\n[3/5] 🎨 이미지 다운로드", flush=True)
    curated = generate_and_save_images(curated)

    print("\n[4/5] 🧹 오래된 이미지 정리", flush=True)
    cleanup_old_images(days_to_keep=30)

    print("\n[5/5] 💾 저장", flush=True)
    save_data(curated)

    end_time = datetime.now(KST).strftime("%H:%M:%S")

    print(f"\n🎉 완료! {len(curated['cards'])}개 카드", flush=True)
    print(f"⏰ 종료 시간: {end_time}", flush=True)

    print("\n📨 카카오 메시지 전송", flush=True)
    send_both_messages()


if __name__ == "__main__":
    main()
