"""
News.pic 일일 생성 스크립트
매일 GitHub Actions가 이걸 실행해서 그날의 뉴스 인포그래픽 데이터를 만듭니다.

흐름:
1. 네이버에서 오늘 주요 뉴스 수집
2. Gemini로 5~7개 선별 + 카드 데이터 생성
3. 각 뉴스마다 Pollinations로 이미지 URL 생성
4. data/YYYY-MM-DD.json 으로 저장
"""

import os
import json
import urllib.parse
import requests
from datetime import datetime, timezone, timedelta
import google.generativeai as genai

# ===== 환경변수 (GitHub Secrets에서 읽어옴) =====
NAVER_CLIENT_ID = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
NAVER_CLIENT_SECRET = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()

# 한국 시간
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

# ===== 1. 네이버에서 뉴스 수집 =====
def fetch_news():
    """네이버 검색 API로 카테고리별 주요 뉴스 수집"""
    categories = ["정치", "경제", "IT", "사회", "세계", "문화"]
    all_news = []

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    for cat in categories:
        url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(cat)}&display=15&sort=date"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            items = r.json().get("items", [])
            for item in items:
                # HTML 태그 제거
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


# ===== 2. Gemini로 큐레이션 + 카드 데이터 생성 =====
def curate_with_gemini(news_list):
    """Gemini가 좋은 뉴스 5~7개 선별하고 인포그래픽 카드 데이터로 변환"""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # 뉴스 목록을 텍스트로 변환
    news_text = "\n\n".join([
        f"[{i}] ({n['category_hint']}) {n['title']}\n   설명: {n['description']}\n   링크: {n['link']}"
        for i, n in enumerate(news_list[:60])  # 너무 많으면 토큰 초과
    ])

    prompt = f"""당신은 뉴스 큐레이터입니다. 아래 뉴스 목록 중 오늘의 인포그래픽 카드로 만들 5개를 선별하세요.

선별 기준:
1. 많은 사람에게 영향을 주는 중요한 뉴스
2. 인포그래픽으로 표현 가능 (숫자, 비교, 타임라인, 비율 등이 있어야 함)
3. 카테고리 다양하게 분산 (한 카테고리에 몰리지 않게)
4. 다음은 무조건 제외:
   - 사망/사고/범죄 관련 뉴스
   - 운세/별자리/연예 가십
   - 광고성 보도
   - 차별/혐오 가능성 있는 내용

선별된 각 뉴스에 대해 다음 JSON 형식으로 반환하세요. 다른 텍스트 없이 JSON만:

{{
  "cards": [
    {{
      "id": "고유ID (영어 소문자, 예: ceasefire)",
      "category": "world|economy|tech|society|life",
      "category_label": "🌍 국제|💰 경제|💻 기술|🏛 사회|🌱 라이프",
      "viz_type": "timeline|bar|donut|grid|flow",
      "title": "카드 제목 (이모지 포함, 20자 이내)",
      "subtitle": "한 줄 설명 (30자 이내, 이탤릭체로 들어감)",
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

뉴스 목록:
{news_text}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # ```json 블록 제거
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)
        print(f"✅ Gemini가 {len(data.get('cards', []))}개 카드 생성")
        return data
    except Exception as e:
        print(f"❌ Gemini 큐레이션 실패: {e}")
        print(f"응답 내용: {text[:500] if 'text' in dir() else 'N/A'}")
        return {"cards": []}


# ===== 3. 이미지 URL 생성 (Pollinations) =====
def add_image_urls(curated_data):
    """각 카드에 Pollinations 이미지 URL 추가"""
    for card in curated_data.get("cards", []):
        prompt = card.get("image_prompt", "cute pastel infographic")
        # 일관된 스타일을 위한 공통 접미사
        full_prompt = f"{prompt}, cute hand-drawn infographic style, pastel colors, cream background, soft shadows, rounded shapes, no text, no words, editorial illustration"
        encoded = urllib.parse.quote(full_prompt)
        # seed를 카드 id로 고정하면 매번 같은 이미지 (캐싱 효과)
        seed = abs(hash(card.get("id", "default"))) % 100000
        card["image_url"] = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"
    return curated_data


# ===== 4. 결과 저장 =====
def save_data(data):
    """data/YYYY-MM-DD.json 으로 저장 + latest.json 업데이트"""
    data["date"] = TODAY
    data["generated_at"] = datetime.now(KST).isoformat()

    os.makedirs("data", exist_ok=True)

    # 날짜별 파일
    daily_path = f"data/{TODAY}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 저장됨: {daily_path}")

    # latest.json (웹사이트가 처음 로드할 때 읽는 파일)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ latest.json 업데이트")


# ===== 메인 실행 =====
def main():
    print(f"🌅 {TODAY} 뉴스 생성 시작")

    # 환경변수 확인
    if not all([NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY]):
        print("❌ 환경변수가 설정되지 않았어요!")
        print(f"   NAVER_CLIENT_ID: {'✓' if NAVER_CLIENT_ID else '✗'}")
        print(f"   NAVER_CLIENT_SECRET: {'✓' if NAVER_CLIENT_SECRET else '✗'}")
        print(f"   GEMINI_API_KEY: {'✓' if GEMINI_API_KEY else '✗'}")
        return

    # 1. 뉴스 수집
    news = fetch_news()
    if not news:
        print("❌ 뉴스를 가져오지 못했어요")
        return

    # 2. 큐레이션
    curated = curate_with_gemini(news)
    if not curated.get("cards"):
        print("❌ 큐레이션 실패")
        return

    # 3. 이미지 URL 추가
    curated = add_image_urls(curated)

    # 4. 저장
    save_data(curated)

    print(f"🎉 완료! {len(curated['cards'])}개 카드 생성됨")


if __name__ == "__main__":
    main()
