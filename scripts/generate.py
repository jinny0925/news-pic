"""
News.pic 일일 생성 스크립트 (v2: 이미지 미리 다운로드)

흐름:
1. 네이버에서 오늘 주요 뉴스 수집
2. Gemini로 카테고리별 2~3개씩 12~15개 + 헤드라인 1개 선별
3. Pollinations에서 그림 실제로 다운로드 → data/images/YYYY-MM-DD/ 저장
4. 30일 지난 이미지 자동 삭제
5. data/YYYY-MM-DD.json 으로 저장
"""

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

# 한국 시간
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

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
            print(f"⚠️ {cat} 카테고리 수집 실패: {e}")
            continue

    print(f"✅ 총 {len(all_news)}개 뉴스 수집")
    return all_news


# ===== 2. Gemini로 큐레이션 =====
def curate_with_gemini(news_list):
    """Gemini가 카테고리별 2~3개씩 + 헤드라인 1개를 선별"""
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
        response = model.generate_content(prompt)
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

        print(f"✅ Gemini가 총 {len(cards)}개 카드 생성")
        print(f"   카테고리별: {cat_counts}")
        print(f"   헤드라인: {headline_count}개")

        return data
    except Exception as e:
        print(f"❌ Gemini 큐레이션 실패: {e}")
        print(f"응답 내용: {text[:500] if 'text' in dir() else 'N/A'}")
        return {"cards": []}


# ===== 3. 이미지 다운로드 (Pollinations) =====
def download_image(url, save_path, max_retries=3):
    """Pollinations에서 이미지 다운로드. 실패 시 재시도."""
    for attempt in range(max_retries):
        try:
            # Pollinations은 첫 요청 시 그림 생성하느라 시간이 걸림 (최대 60초)
            r = requests.get(url, timeout=90, stream=True)
            r.raise_for_status()

            # 진짜 이미지인지 확인 (content-type)
            content_type = r.headers.get('content-type', '')
            if 'image' not in content_type:
                print(f"   ⚠️ 이미지가 아님 (content-type: {content_type}), 재시도...")
                time.sleep(3)
                continue

            # 저장
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 파일 크기 확인 (너무 작으면 실패한 것)
            file_size = os.path.getsize(save_path)
            if file_size < 1000:  # 1KB 미만이면 실패
                print(f"   ⚠️ 파일이 너무 작음 ({file_size} bytes), 재시도...")
                os.remove(save_path)
                time.sleep(3)
                continue

            return True
        except Exception as e:
            print(f"   ⚠️ 시도 {attempt+1}/{max_retries} 실패: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return False


def generate_and_save_images(curated_data):
    """각 카드의 이미지를 Pollinations에서 다운로드해서 GitHub에 저장"""
    # 오늘 날짜 폴더 생성
    image_dir = f"data/images/{TODAY}"
    os.makedirs(image_dir, exist_ok=True)

    cards = curated_data.get("cards", [])
    success_count = 0

    for idx, card in enumerate(cards):
        card_id = card.get("id", f"card-{idx}")
        prompt = card.get("image_prompt", "cute pastel infographic")

        # 일관된 스타일을 위한 공통 접미사
        full_prompt = f"{prompt}, cute hand-drawn infographic style, pastel colors, cream background, soft shadows, rounded shapes, no text, no words, editorial illustration"
        encoded = urllib.parse.quote(full_prompt)
        seed = abs(hash(card_id)) % 100000
        pollinations_url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"

        # 저장할 파일 경로
        filename = f"{card_id}.jpg"
        save_path = f"{image_dir}/{filename}"
        github_path = f"data/images/{TODAY}/{filename}"

        print(f"🎨 [{idx+1}/{len(cards)}] {card_id} 이미지 다운로드 중...")

        if download_image(pollinations_url, save_path):
            # GitHub Pages에서 접근 가능한 상대 경로 사용
            card["image_url"] = github_path
            success_count += 1
            print(f"   ✅ 저장됨: {github_path}")
        else:
            # 다운로드 실패 시 원래 Pollinations URL을 백업으로 사용
            card["image_url"] = pollinations_url
            print(f"   ⚠️ 다운로드 실패, Pollinations URL을 백업으로 사용")

    print(f"\n📊 이미지 다운로드 결과: {success_count}/{len(cards)} 성공")
    return curated_data


# ===== 4. 오래된 이미지 자동 정리 =====
def cleanup_old_images(days_to_keep=30):
    """30일 지난 이미지 폴더 삭제 (저장 공간 관리)"""
    images_root = "data/images"
    if not os.path.exists(images_root):
        return

    cutoff_date = datetime.now(KST) - timedelta(days=days_to_keep)
    deleted_count = 0

    for folder_name in os.listdir(images_root):
        folder_path = os.path.join(images_root, folder_name)
        if not os.path.isdir(folder_path):
            continue

        # 폴더 이름이 YYYY-MM-DD 형식인지 확인
        try:
            folder_date = datetime.strptime(folder_name, "%Y-%m-%d").replace(tzinfo=KST)
            if folder_date < cutoff_date:
                shutil.rmtree(folder_path)
                deleted_count += 1
                print(f"🗑️ 오래된 이미지 삭제: {folder_name}")
        except ValueError:
            # 날짜 형식이 아닌 폴더는 건너뜀
            continue

    if deleted_count > 0:
        print(f"✅ 총 {deleted_count}개 오래된 폴더 삭제")


# ===== 5. 결과 저장 =====
def save_data(data):
    """data/YYYY-MM-DD.json 으로 저장 + latest.json 업데이트"""
    data["date"] = TODAY
    data["generated_at"] = datetime.now(KST).isoformat()

    os.makedirs("data", exist_ok=True)

    daily_path = f"data/{TODAY}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 저장됨: {daily_path}")

    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ latest.json 업데이트")


# ===== 메인 실행 =====
def main():
    print(f"🌅 {TODAY} 뉴스 생성 시작\n")

    # 환경변수 확인
    if not all([NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY]):
        print("❌ 환경변수가 설정되지 않았어요!")
        return

    # 1. 뉴스 수집
    print("=" * 50)
    print("📰 1단계: 뉴스 수집")
    print("=" * 50)
    news = fetch_news()
    if not news:
        print("❌ 뉴스를 가져오지 못했어요")
        return

    # 2. 큐레이션
    print("\n" + "=" * 50)
    print("🤖 2단계: AI 큐레이션")
    print("=" * 50)
    curated = curate_with_gemini(news)
    if not curated.get("cards"):
        print("❌ 큐레이션 실패")
        return

    # 3. 이미지 다운로드
    print("\n" + "=" * 50)
    print("🎨 3단계: 이미지 생성 및 다운로드")
    print("=" * 50)
    curated = generate_and_save_images(curated)

    # 4. 오래된 이미지 정리
    print("\n" + "=" * 50)
    print("🧹 4단계: 오래된 이미지 정리")
    print("=" * 50)
    cleanup_old_images(days_to_keep=30)

    # 5. 저장
    print("\n" + "=" * 50)
    print("💾 5단계: 데이터 저장")
    print("=" * 50)
    save_data(curated)

    print(f"\n🎉 완료! {len(curated['cards'])}개 카드 생성됨")


if __name__ == "__main__":
    main()
