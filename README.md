# 📰 News.pic

매일 아침 자동으로 큐레이션되는 뉴스 인포그래픽.

## 🎯 어떻게 작동해요?

```
매일 아침 7시 (한국시간)
  ↓
GitHub Actions가 자동 실행
  ↓
1. 네이버 뉴스 API에서 오늘 뉴스 수집
2. Google Gemini가 5개 선별 + 인포그래픽 데이터 생성
3. Pollinations.ai가 각 뉴스 그림 생성
4. data/YYYY-MM-DD.json 으로 저장
  ↓
index.html이 데이터를 읽어 보여줌
```

## 🚀 셋업 방법

### 1. API 키 준비
- 네이버 검색 API: https://developers.naver.com
- Google Gemini: https://aistudio.google.com

### 2. GitHub Secrets 설정
저장소 → Settings → Secrets and variables → Actions → New repository secret

다음 3개 추가:
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`  
- `GEMINI_API_KEY`

### 3. GitHub Pages 켜기 (웹사이트 보려면)
저장소 → Settings → Pages → Source: `main` 브랜치 / 폴더: `/ (root)` → Save

몇 분 뒤 `https://본인아이디.github.io/news-pic/` 으로 접속 가능.

### 4. 첫 실행
저장소 → Actions 탭 → "Daily News Generation" → "Run workflow" 버튼 → 실행

3~5분 후 `data/` 폴더에 JSON 파일 생성됨.

## 📅 이후

- 매일 아침 7시(한국시간) 자동 실행
- 실패해도 전날 데이터로 표시됨
- Actions 탭에서 실행 로그 확인 가능

## 🛠 문제가 있을 때

- Actions 탭에서 빨간색 X 표시가 뜨면 클릭해서 에러 메시지 확인
- 에러 메시지를 Claude에게 그대로 전달하면 고쳐줍니다

## 💰 비용

전부 무료 티어 사용:
- 네이버 API: 25,000건/일 무료
- Gemini: 일 1,500회 무료  
- Pollinations: 무제한 무료
- GitHub Actions: 월 2,000분 무료
- GitHub Pages: 무료
