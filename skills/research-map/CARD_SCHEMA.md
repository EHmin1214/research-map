# 세션 카드 스키마 (research-map)

각 세션 digest 를 읽고 아래 JSON 하나를 `~/.claude/research-map/cards/<첫 sessionId 8자>.json` 에 저장한다.
모든 문장은 한국어. 수치·파일 경로·날짜는 digest 에 실제로 있는 것만 쓴다(추정 금지).

{
  "sessionIds": ["전체 세션 id 문자열들"],
  "period": "YYYY-MM-DD ~ YYYY-MM-DD",
  "oneLiner": "이 세션(들)이 무엇을 했는지 한 문장",
  "threads": [
    {
      "title": "연구 갈래 이름 (짧게, 15자 내외)",
      "topic": "상위 주제 (예: 몽타주 최적화 / 랫 실험 / 온도 게이트 / 도구 개발 / 논문·포스터 / 인프라)",
      "goal": "왜 이걸 했는가 (가설·질문)",
      "steps": ["시간순으로 무엇을 했는지, 3~8개, 각 1문장, 날짜 붙이기"],
      "outcome": "결론 또는 결과 (수치 포함)",
      "status": "confirmed | refuted | withdrawn | inconclusive | ongoing | done | abandoned",
      "keyNumbers": ["핵심 수치와 그 의미 (예: 'MD 0.31 V/m @ 2mA — 안전 전류 상한')"],
      "openQuestions": ["더 파볼 수 있는 것, 미해결, 다음 단계"],
      "pitfalls": ["잘못 갔던 길·되돌린 결정·함정"],
      "files": ["이 갈래에서 만들거나 고친 핵심 파일 경로 (최대 8개)"],
      "docs": ["보고서·md·pptx·pdf 등 산출 문서 경로"],
      "dates": "YYYY-MM-DD ~ YYYY-MM-DD"
    }
  ],
  "decisions": ["YYYY-MM-DD: 사용자가 내린 방향 결정 (무엇을 버리고 무엇을 택했는지)"],
  "artifacts": ["세션이 남긴 최종 산출물 경로"],
  "relatedMemory": ["관련 메모리 파일 이름 (있으면)"]
}
