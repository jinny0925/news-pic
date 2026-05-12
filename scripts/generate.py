def load_latest_as_fallback():
    """Gemini 실패 시 기존 latest.json을 백업으로 사용"""
    try:
        if os.path.exists("data/latest.json"):
            with open("data/latest.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            print("⚠️ Gemini 실패로 기존 latest.json 백업 사용", flush=True)
            return data
    except Exception as e:
        print(f"⚠️ latest.json 백업 로드 실패: {e}", flush=True)

    return {"cards": []}


def extract_json_from_text(text):
    """Gemini 응답에서 JSON만 안전하게 추출"""
    text = text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def curate_with_gemini(news_list):
    """Gemini가 카테고리별 2~3개씩 + 헤드라인 1개를 선별"""
    print("🤖 Gemini API 호출 시작...", flush=True)

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # 140개 수집은 유지하되, 설명이 너무 길면 잘라서 타임아웃 위험 감소
    news_text = "\n\n".join([
        f"[{i}] ({n['category_hint']}) {n['title']}\n"
        f"설명: {(n['description'] or '')[:180]}\n"
        f"링크: {n['link']}"
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

2. 그중 가장 중요한 1개를 "is_headline": true 로 표시
3. 인포그래픽으로 표현 가능해야 함
4. 다음은 제외:
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
                raise ValueError("Gemini 응답에 cards가 없음")

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

    # 완전 실패해도 워크플로우가 멈추지 않게 기존 latest 사용
    return load_latest_as_fallback()
