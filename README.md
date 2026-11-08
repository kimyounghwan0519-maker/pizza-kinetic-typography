# 피자 프랜차이즈 EDA · 30초 키네틱 타이포그래피

피자 프랜차이즈 9개 매장의 2020-01~2026-08 월별 실적(가상 데이터)에서 뽑은 시사점 3개를 30초 키네틱 타이포그래피로 만든 영상입니다. 화면은 코드로만 그렸습니다.

- 영상: `kinetic_insights.mp4` (1920×1080, 30fps, 한국어 내레이션)
- 웹 페이지: `index.html` (GitHub Pages)
- 강조색: 커니 퍼플 `#7823DC`

## 다시 만들기 (macOS)

```bash
pip install pillow numpy imageio-ffmpeg
python3 vo.py 182          # 'say -v Yuna'로 내레이션 생성 → vo/
python3 kinetic.py         # kinetic_insights.mp4 렌더링
python3 kinetic.py preview 4.3 12.0   # 특정 시각 프레임 PNG
```

장면 타이밍은 `vo/meta.json`의 내레이션 길이에서 자동 계산됩니다.
