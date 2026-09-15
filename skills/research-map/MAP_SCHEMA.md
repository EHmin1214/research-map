# map.json 스키마 (research-map)

`~/.claude/research-map/map.json` 은 연구 지도의 단일 진실 원천이다. 렌더러는 이 파일만 읽는다.
LLM 이 세션 카드(`cards/*.json`)·메모리·문서를 읽고 이 파일을 **갱신**한다(덮어쓰지 말고 병합).

```json
{
  "version": 1,
  "title": "TIS 연구 지도",
  "updatedAt": "2026-09-15",
  "nodes": [ { ...node } ]
}
```

## node

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | ✔ | 안정적인 slug (영문 소문자·숫자·하이픈). 한 번 정하면 바꾸지 않는다 — 링크·북마크가 이 값을 쓴다 |
| `parent` | ✔ | 부모 node id. 최상위 주제는 `null` |
| `type` | ✔ | `topic` 주제 · `direction` 방향/가설 · `process` 과정/실험 · `result` 결과 · `open` 열린 질문/다음 단계 · `artifact` 산출물(보고서·코드·데이터) |
| `title` | ✔ | 20자 내외. 카드에 두 줄까지 보인다 |
| `status` | ✔ | `ongoing` 진행 중 · `done` 완료 · `confirmed` 확인됨 · `refuted` 반증 · `withdrawn` 철회 · `inconclusive` 미결 · `abandoned` 중단 · `open` 열림 · `blocked` 막힘 · `planned` 계획 |
| `period` | | `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}`. end 생략 가능 |
| `summary` | ✔ | 1~3문장. 카드 툴팁·목록·패널 상단 |
| `detail` | | 마크다운(문단·`**굵게**`·`- 목록`·`### 소제목`·`` `코드` ``). 무엇을·왜·어떻게·결과·교훈 |
| `evidence` | | 문자열 배열. 근거 수치·인용. 예: `"MD 0.31 V/m @ 2 mA (안전 상한)"` |
| `next` | | 문자열 배열. 이 노드에서 더 파볼 수 있는 것. `open` 노드를 따로 만들 정도가 아닌 작은 것 |
| `sources` | | `[{"kind":"session|file|doc|memory|url","ref":"...","label":"...","note":"..."}]`. session 은 sessionId 전체, file/doc 은 절대경로, memory 는 파일명, url 은 http(s) |
| `links` | | 다른 node id 배열 (교차 관계: 반증 근거, 재사용한 도구 등) |
| `tags` | | 자유 태그 |
| `order` | | 형제 간 정렬 키(숫자). 없으면 period.start → title 순 |

## 작성 규칙

1. **트리는 "주제 → 방향 → 과정 → 결과/열린 질문"** 이 기본 깊이다. 산출물은 해당 과정·결과 아래에 붙인다. 4~5단계를 넘기지 않는다.
2. **결과 노드는 status 를 정직하게.** 철회·반증된 것도 지우지 않고 `withdrawn`/`refuted` 로 남긴다 — 다시 같은 길을 가지 않게 하는 것이 이 지도의 목적이다.
3. **모든 result·process 노드에 sources 최소 1개.** 세션 id 가 있으면 반드시 넣는다(`claude --resume` 로 이어갈 수 있게).
4. **숫자는 evidence 에.** summary/detail 본문에는 수치를 늘어놓지 않는다.
5. **갱신 시**: 기존 id 유지, 새 세션에서 나온 내용은 기존 노드에 붙이거나(period.end·evidence·sources 추가) 새 노드를 만든다. status 가 바뀌면 detail 에 `### 변경 이력` 으로 날짜와 이유를 남긴다.
6. 최상위 `topic` 은 5~9개를 넘기지 않는다. 그 이상이면 상위 주제로 묶는다.
