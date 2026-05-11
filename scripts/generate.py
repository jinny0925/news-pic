"""
News.pic 일일 생성 스크립트 (v3: 안정성 개선)

개선점:
- print 출력 즉시 보이게 (버퍼링 해제)
- Pollinations timeout 단축 (30초)
- 재시도 횟수 줄임 (2회)
- 실패해도 다음 이미지로 계속 진행
"""

import sys
# print를 버퍼링 없이 즉시 출력 (GitHub Actions에서 실시간 로그 보기)
sys.stdout.reconfigure(line_buffering=True)

import os
import json
import urllib.parse
import requests
import time
import shutil
from datetime import datetime, timezone, timedelta
import google.generativeai as genai
def send_kakao_message(text):
    access_token = os.environ["KAKAO_ACCESS_TOKEN"]

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

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
        "template_object": json.dumps(template)
    }

    response = requests.post(url, headers=headers, data=data)

    print(response.status_code)
    print(response.text)
    

# ===== 환경변수 =====
NAVER_CLIENT_ID = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
NAVER_CLIENT_SECRET = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()

# 한국 시간
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

def get_kakao_access_token():
    url = "https://kauth.kakao.com/oauth/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_CLIENT_ID"],
        "client_secret": os.environ["KAKAO_CLIENT_SECRET"],
        "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
    }

    response = requests.post(url, data=data)
    print("🔑 카카오 토큰 갱신 결과:", response.status_code, response.text, flush=True)
    response.raise_for_status()

    return response.json()["access_token"]


def send_kakao_friend_message(text):
    access_token = get_kakao_access_token()
    friend_uuid = os.environ["KAKAO_FRIEND_UUID"]

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

    response = requests.post(url, headers=headers, data=data)
    print("📩 카카오 친구 메시지 결과:", response.status_code, response.text, flush=True)
    response.raise_for_status()

# ===== 1. 네이버에서 뉴스 수집 =====
def fetch_news():
    """네이버 검색 API로 카테고리별 주요 뉴스 수집"""
    categories = ["정치", "경제", "IT", "사회", "세계", "문화", "라이프"]
    all_news = []

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    for cat in categories:
        url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(cat)}&display=20&sort=date"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            items = r.json().get("items", [])
            for item in items:
                title = item["title"].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
                desc = item["description"].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
                all_news.append({
                    "category_hint": cat,
                    "title": title,
                    "description": desc,
                    "link": item["link"],
                    "pubDate": item.get("pubDate", "")
                })
        except Exception as e:
            print(f"⚠️ {cat} 카테고리 수집 실패: {e}", flush=True)
            continue

    print(f"✅ 총 {len(all_news)}개 뉴스 수집", flush=True)
    return all_news


# ===== 2. Gemini로 큐레이션 =====
def curate_with_gemini(news_list):
    """Gemini가 카테고리별 2~3개씩 + 헤드라인 1개를 선별"""
    print("🤖 Gemini API 호출 시작...", flush=True)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    news_text = "\n\n".join([
        f"[{i}] ({n['category_hint']}) {n['title']}\n   설명: {n['description']}\n   링크: {n['link']}"
        for i, n in enumerate(news_list[:100])
    ])

    prompt = f"""당신은 뉴스 큐레이터입니다. 아래 뉴스 목록 중 오늘의 인포그래픽 카드로 만들 뉴스를 선별하세요.

선별 기준:
1. 다음 5개 카테고리에서 각 2~3개씩 선별 (총 12~15개):
   - world (국제): 국제 정치, 외교, 세계 이슈
   - economy (경제): 주식, 부동산, 산업, 금융
   - tech (기술): IT, AI, 과학기술, 신제품
   - society (사회): 정치, 사회 이슈, 정책
   - life (라이프): 문화, 트렌드, 일상

2. 그중 가장 중요한 1개를 "is_headline": true 로 표시 (헤드라인)
3. 인포그래픽으로 표현 가능 (숫자, 비교, 타임라인, 비율 등이 있어야 함)
4. 다음은 무조건 제외:
   - 사망/사고/범죄 관련 뉴스
   - 운세/별자리/연예 가십
   - 광고성 보도
   - 차별/혐오 가능성 있는 내용

선별된 각 뉴스에 대해 다음 JSON 형식으로 반환하세요. 다른 텍스트 없이 JSON만:

{{
  "cards": [
    {{
      "id": "고유ID (영어 소문자, 예: world-ceasefire)",
      "is_headline": false,
      "category": "world|economy|tech|society|life",
      "category_label": "🌍 국제|💰 경제|💻 기술|🏛 사회|🌱 라이프 중 하나",
      "viz_type": "timeline|bar|donut|grid|flow",
      "title": "카드 제목 (이모지 포함, 20자 이내)",
      "subtitle": "한 줄 설명 (30자 이내)",
      "viz_data": {{
        "stats": [
          {{"value": "3일", "label": "기간"}},
          {{"value": "2국", "label": "참여"}},
          {{"value": "1170+", "label": "개전 일"}}
        ],
        "main_number": "+47%",
        "main_text": "주요 수치 한 줄 설명"
      }},
      "image_prompt": "Pollinations에 보낼 영어 프롬프트 (귀여운 인포그래픽 스타일, 텍스트 없이, 파스텔 톤)",
      "detail": {{
        "summary": "한 줄 요약 (2-3문장)",
        "points": ["핵심 포인트 1", "핵심 포인트 2", "핵심 포인트 3", "핵심 포인트 4"],
        "quote": "관련 인용구 또는 의미있는 한 마디",
        "context": "왜 이게 중요한지 배경 (2-3문장)",
        "source_url": "원문 링크"
      }}
    }}
  ]
}}

⚠️ 중요:
- 카테고리당 정확히 2~3개씩 골라주세요
- 총 12~15개 사이여야 합니다
- 정확히 1개만 is_headline=true로 표시
- 같은 카테고리 안에서 id가 중복되지 않게
- category와 category_label은 정확히 위 5개 중 하나여야 함

뉴스 목록:
{news_text}
"""

    try:
        # request_options로 타임아웃 설정 (5분)
        response = model.generate_content(
            prompt,
            request_options={"timeout": 300}
        )
        text = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)
        cards = data.get("cards", [])

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
        print(f"❌ Gemini 큐레이션 실패: {e}", flush=True)
        return {"cards": []}


# ===== 3. 이미지 다운로드 =====
def download_image(url, save_path, max_retries=3):
    """Pollinations에서 이미지 다운로드. 429 에러 시 길게 대기 후 재시도."""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=60, stream=True)

            # 429 (Too Many Requests) 처리
            if r.status_code == 429:
                wait_time = 30 * (attempt + 1)  # 30초, 60초, 90초로 점점 길게
                print(f"      ⏳ 429 Too Many Requests, {wait_time}초 대기...", flush=True)
                time.sleep(wait_time)
                continue

            r.raise_for_status()

            content_type = r.headers.get('content-type', '')
            if 'image' not in content_type:
                print(f"      ⚠️ 이미지가 아님 ({content_type})", flush=True)
                time.sleep(5)
                continue

            with open(save_path, 'wb') as f:
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
            print(f"      ⚠️ 시도 {attempt+1}/{max_retries} timeout", flush=True)
            time.sleep(10)
        except Exception as e:
            print(f"      ⚠️ 시도 {attempt+1}/{max_retries} 실패: {e}", flush=True)
            time.sleep(10)

    return False


def generate_and_save_images(curated_data):
    """각 카드의 이미지를 다운로드해서 저장"""
    image_dir = f"data/images/{TODAY}"
    os.makedirs(image_dir, exist_ok=True)

    cards = curated_data.get("cards", [])
    success_count = 0
    start_time = time.time()

    for idx, card in enumerate(cards):
        card_id = card.get("id", f"card-{idx}")
        prompt = card.get("image_prompt", "cute pastel infographic")

        full_prompt = f"{prompt}, cute hand-drawn infographic style, pastel colors, cream background, soft shadows, rounded shapes, no text, no words, editorial illustration"
        encoded = urllib.parse.quote(full_prompt)
        seed = abs(hash(card_id)) % 100000
        pollinations_url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"

        filename = f"{card_id}.jpg"
        save_path = f"{image_dir}/{filename}"
        github_path = f"data/images/{TODAY}/{filename}"

        elapsed = int(time.time() - start_time)
        print(f"🎨 [{idx+1}/{len(cards)}] {card_id} ({elapsed}s 경과)", flush=True)

        if download_image(pollinations_url, save_path):
            card["image_url"] = github_path
            success_count += 1
            print(f"      ✅ 저장됨", flush=True)
        else:
            # 실패 시 Pollinations URL을 백업으로 사용
            card["image_url"] = pollinations_url
            print(f"      ⚠️ 다운로드 실패, 백업 URL 사용", flush=True)

        # 다음 이미지 요청 전에 잠시 대기 (Pollinations 429 방지)
        if idx < len(cards) - 1:
            time.sleep(10)

    print(f"\n📊 이미지 다운로드: {success_count}/{len(cards)} 성공", flush=True)
    return curated_data


# ===== 4. 오래된 이미지 정리 =====
def cleanup_old_images(days_to_keep=30):
    """30일 지난 이미지 폴더 삭제"""
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
    print(f"✅ latest.json 업데이트", flush=True)


# ===== 메인 =====
def main():
    print(f"🌅 {TODAY} 뉴스 생성 시작", flush=True)
    print(f"⏰ 시작 시간: {datetime.now(KST).strftime('%H:%M:%S')}", flush=True)

    if not all([NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY]):
        print("❌ 환경변수가 설정되지 않았어요!", flush=True)
        return

    # 1. 뉴스 수집
    print("\n[1/5] 📰 뉴스 수집", flush=True)
    news = fetch_news()
    if not news:
        print("❌ 뉴스를 가져오지 못했어요", flush=True)
        return

    # 2. 큐레이션
    print("\n[2/5] 🤖 AI 큐레이션", flush=True)
    curated = curate_with_gemini(news)
    if not curated.get("cards"):
        print("❌ 큐레이션 실패", flush=True)
        return

    # 3. 이미지 다운로드
    print("\n[3/5] 🎨 이미지 다운로드", flush=True)
    curated = generate_and_save_images(curated)

    # 4. 정리
    print("\n[4/5] 🧹 오래된 이미지 정리", flush=True)
    cleanup_old_images(days_to_keep=30)

    # 5. 저장
    print("\n[5/5] 💾 저장", flush=True)
    save_data(curated)

    end_time = datetime.now(KST).strftime('%H:%M:%S')
    print(f"\n🎉 완료! {len(curated['cards'])}개 카드", flush=True)
    print(f"⏰ 종료 시간: {end_time}", flush=True)
    send_kakao_friend_message(f"📰 News.pic 업데이트 완료! ({TODAY})")
    
    send_kakao_message("페이지 업데이트 완료!")
    


if __name__ == "__main__":
    main()
