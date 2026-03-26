---
title: "CanonCode의 Rust 엔진 — .lex 파서부터 조항 충돌 감지까지"
date: 2026-03-19
draft: false
tags: ["CanonCode", "Rust", "Parser", "Architecture", "CLI"]
description: "CanonCode의 핵심인 Rust 기반 lex_engine의 내부 구조. JSON 파서, 조항 의존성 그래프, 헌법-법률 충돌 감지, CLI 인터페이스까지 설계 결정과 삽질을 기록했다."
---

[CanonCode](https://github.com/seunghan91/canoncode)를 소개하는 [이전 글](/posts/canoncode-spec-vs-code/)에서 "2,800줄의 코드를 160줄의 명세로 압축했다"는 실험을 다뤘다. 이번에는 그 명세를 읽고 검증하는 엔진의 내부를 파헤친다.

왜 Rust인가, 파싱은 어떻게 하는가, 조항 간 충돌은 어떻게 감지하는가. 설계 결정마다 "다른 선택지도 있었는데 왜 이걸 골랐는지"를 함께 기록한다.

---

## 왜 Rust인가

CanonCode의 엔진은 3가지 역할을 한다:

1. `.lex` 파일 파싱 및 구조 검증
2. 조항 간 의존성 그래프 빌드
3. 헌법-법률 계층 간 충돌 감지

처음에는 TypeScript로 작성했다. Node.js 생태계에 익숙하고, JSON 파싱이 네이티브이니까. 한 달 정도 쓰다가 Rust로 재작성했다. 이유:

| 기준 | TypeScript | Rust |
|------|-----------|------|
| 파싱 속도 (1000 조항) | ~420ms | ~8ms |
| 바이너리 배포 | Node 런타임 필요 | 단일 바이너리 |
| 타입 안전성 | 런타임 에러 가능 | 컴파일 타임 보장 |
| 의존성 그래프 | 객체 참조 → GC 부담 | 소유권으로 명시적 관리 |

50배 속도 차이가 결정적이었다. `.lex` 파일이 커지면 IDE 플러그인에서 실시간 검증이 필요한데, 400ms면 타이핑할 때마다 버벅인다. 8ms면 체감이 없다.

단일 바이너리 배포도 중요했다. `npx canoncode`로 쓸 수 있어야 하는데, Node 래퍼에서 Rust 바이너리를 호출하는 구조가 TypeScript 순수 구현보다 실행이 빠르고 신뢰도가 높다.

---

## .lex 파일 구조

`.lex` 파일은 JSON이다. 마크다운이나 YAML이 더 읽기 편하지만, 파싱 편의성을 우선했다. (이건 솔직히 나중에 후회할 수도 있다.)

```json
{
  "meta": {
    "project": "LaunchCrew",
    "version": "1.0.0",
    "language": "ko"
  },
  "constitution": [
    {
      "id": "CONST-001",
      "content": "모든 금전 거래는 에스크로를 통해야 한다",
      "rationale": "직접 송금 시 분쟁 해결 불가"
    }
  ],
  "acts": [
    {
      "id": "ACT-001",
      "title": "QA 공고 생성",
      "clauses": [
        {
          "id": "CL-001-1",
          "content": "공고 생성 시 결제 수단(point/card)을 선택한다",
          "references": ["CONST-001"]
        }
      ]
    }
  ],
  "case_law": [
    {
      "id": "CASE-001",
      "situation": "잔액 부족 상태에서 공고 생성 시도",
      "ruling": "422 에러 반환, 공고 생성 롤백",
      "references": ["CL-001-2", "CONST-001"]
    }
  ]
}
```

계층 구조: `constitution` → `acts` → `clauses` → `case_law`

모든 조항은 고유 ID를 가지고, `references`로 상위 조항을 참조한다. 이 참조 관계가 의존성 그래프의 기반이다.

---

## 파서 구조

Rust에서 JSON 파싱은 `serde`가 표준이다. `.lex`의 구조를 Rust 타입으로 매핑했다.

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
pub struct LexDocument {
    pub meta: Meta,
    pub constitution: Vec<Article>,
    pub acts: Vec<Act>,
    #[serde(default)]
    pub rules: Vec<Rule>,
    #[serde(default)]
    pub appendices: Vec<Appendix>,
    #[serde(default)]
    pub case_law: Vec<CaseLaw>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Article {
    pub id: String,
    pub content: String,
    #[serde(default)]
    pub rationale: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Clause {
    pub id: String,
    pub content: String,
    #[serde(default)]
    pub references: Vec<String>,
    #[serde(default)]
    pub constraints: Vec<Constraint>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CaseLaw {
    pub id: String,
    pub situation: String,
    pub ruling: String,
    pub references: Vec<String>,
}
```

`serde`의 `#[serde(default)]`를 적극적으로 썼다. `.lex` 파일 작성 시 선택적 필드를 생략할 수 있게 하려고. 처음에는 모든 필드를 필수로 만들었는데, 명세를 점진적으로 작성하는 워크플로우에 맞지 않았다. 헌법 먼저 쓰고, 법률은 나중에 채우고, 판례는 버그가 발견될 때 추가하는 식이다.

파싱 자체는 한 줄이다:

```rust
pub fn parse_lex(content: &str) -> Result<LexDocument, LexError> {
    serde_json::from_str(content)
        .map_err(|e| LexError::ParseError(e.to_string()))
}
```

진짜 복잡한 건 파싱 이후다.

---

## 의존성 그래프

모든 조항의 `references`를 모아서 방향 그래프를 만든다. 이 그래프가 CanonCode의 핵심 자료구조다.

```rust
use std::collections::{HashMap, HashSet};

pub struct DependencyGraph {
    // 조항 ID → 조항 데이터
    nodes: HashMap<String, NodeData>,
    // 조항 ID → 참조하는 조항 ID 목록
    edges: HashMap<String, HashSet<String>>,
    // 역방향: 조항 ID → 이 조항을 참조하는 조항들
    reverse_edges: HashMap<String, HashSet<String>>,
}

impl DependencyGraph {
    pub fn build(doc: &LexDocument) -> Result<Self, LexError> {
        let mut graph = Self::new();

        // 1. 모든 조항을 노드로 등록
        for article in &doc.constitution {
            graph.add_node(&article.id, NodeLevel::Constitution);
        }
        for act in &doc.acts {
            for clause in &act.clauses {
                graph.add_node(&clause.id, NodeLevel::Clause);
            }
        }
        for case in &doc.case_law {
            graph.add_node(&case.id, NodeLevel::CaseLaw);
        }

        // 2. 참조 관계를 엣지로 등록
        for act in &doc.acts {
            for clause in &act.clauses {
                for ref_id in &clause.references {
                    graph.add_edge(&clause.id, ref_id)?;
                }
            }
        }
        for case in &doc.case_law {
            for ref_id in &case.references {
                graph.add_edge(&case.id, ref_id)?;
            }
        }

        // 3. 검증
        graph.validate()?;

        Ok(graph)
    }
}
```

### 그래프 검증

빌드 후 3가지를 확인한다:

```rust
fn validate(&self) -> Result<(), LexError> {
    // 1. 끊어진 참조: 존재하지 않는 ID를 참조
    for (from, refs) in &self.edges {
        for to in refs {
            if !self.nodes.contains_key(to) {
                return Err(LexError::BrokenReference(
                    from.clone(), to.clone()
                ));
            }
        }
    }

    // 2. 순환 참조: A → B → C → A
    self.detect_cycles()?;

    // 3. 계층 위반: 하위 법률이 상위를 건너뛰고 참조
    self.check_hierarchy()?;

    Ok(())
}
```

순환 참조 감지는 DFS(깊이 우선 탐색)로 구현했다. 표준적인 알고리즘이다:

```rust
fn detect_cycles(&self) -> Result<(), LexError> {
    let mut visited = HashSet::new();
    let mut in_stack = HashSet::new();

    for node_id in self.nodes.keys() {
        if !visited.contains(node_id) {
            self.dfs_cycle(node_id, &mut visited, &mut in_stack)?;
        }
    }
    Ok(())
}

fn dfs_cycle(
    &self,
    node: &str,
    visited: &mut HashSet<String>,
    in_stack: &mut HashSet<String>,
) -> Result<(), LexError> {
    visited.insert(node.to_string());
    in_stack.insert(node.to_string());

    if let Some(refs) = self.edges.get(node) {
        for ref_id in refs {
            if !visited.contains(ref_id.as_str()) {
                self.dfs_cycle(ref_id, visited, in_stack)?;
            } else if in_stack.contains(ref_id.as_str()) {
                return Err(LexError::CircularReference(
                    node.to_string(), ref_id.clone()
                ));
            }
        }
    }

    in_stack.remove(node);
    Ok(())
}
```

---

## 충돌 감지

이게 가장 재밌는 부분이다. 헌법에 "잔액은 항상 0 이상"이라고 명시되어 있는데, 새로 추가한 법률이 "환불 시 수수료를 차감한다"면, 차감 후 잔액이 음수가 될 수 있다. 이런 잠재적 충돌을 감지한다.

현재는 키워드 기반 규칙 매칭으로 구현했다. 완전한 의미론적 분석은 아직 멀었지만, 기본적인 패턴은 잡는다.

```rust
pub struct ConflictRule {
    pub constitution_pattern: Vec<String>,  // 헌법 조항의 키워드
    pub clause_pattern: Vec<String>,        // 법률 조항의 키워드
    pub conflict_type: ConflictType,
    pub severity: Severity,
}

// 내장 규칙 예시
fn default_rules() -> Vec<ConflictRule> {
    vec![
        ConflictRule {
            constitution_pattern: vec!["balance".into(), ">= 0".into()],
            clause_pattern: vec!["deduct".into(), "subtract".into(), "차감".into()],
            conflict_type: ConflictType::PotentialViolation,
            severity: Severity::Warning,
        },
        ConflictRule {
            constitution_pattern: vec!["escrow".into(), "에스크로".into()],
            clause_pattern: vec!["direct".into(), "직접".into(), "송금".into()],
            conflict_type: ConflictType::DirectContradiction,
            severity: Severity::Error,
        },
    ]
}
```

솔직히 이 방식은 거칠다. "차감"이라는 단어가 있다고 항상 잔액 음수가 되는 건 아니다. false positive가 꽤 나온다. 하지만 **경고를 무시하는 것은 쉽고, 놓치는 것은 치명적**이라는 철학으로 일단 넓게 잡고 있다.

장기적으로는 LLM을 연동해서 의미론적 충돌을 감지하고 싶다. "이 조항이 헌법 원칙을 위반할 수 있나요?"를 Claude에게 물어보는 식이다. 아직 실험 단계.

---

## CLI 인터페이스

엔진 위에 CLI를 올렸다. `clap` 크레이트 사용.

```rust
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "lex_cli")]
#[command(about = "CanonCode .lex file analyzer")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// .lex 파일 정보 출력
    Info {
        #[arg(short, long)]
        file: String,
    },
    /// 의존성 그래프 검증
    Validate {
        #[arg(short, long)]
        file: String,
    },
    /// 충돌 감지
    Check {
        #[arg(short, long)]
        file: String,
        #[arg(long, default_value = "warning")]
        severity: String,
    },
    /// 의존성 트리 시각화
    Tree {
        #[arg(short, long)]
        file: String,
        #[arg(long)]
        root: Option<String>,
    },
}
```

사용 예시:

```bash
# 파일 정보
$ lex_cli info -f launchcrew.lex
Project: LaunchCrew v1.0.0
Constitution: 5 articles
Acts: 3 (12 clauses)
Rules: 4
Case Law: 6
References: 23 edges

# 검증
$ lex_cli validate -f launchcrew.lex
✅ No broken references
✅ No circular dependencies
✅ Hierarchy valid

# 충돌 감지
$ lex_cli check -f launchcrew.lex
⚠️  CL-003-2 ("수수료 차감") may conflict with CONST-001 ("잔액 >= 0")
    Type: PotentialViolation
    Suggestion: Add guard clause or update case_law

# 의존성 트리
$ lex_cli tree -f launchcrew.lex --root CONST-001
CONST-001: 모든 금전 거래는 에스크로를 통해야 한다
├── CL-001-2: point 타입 공고 시 즉시 에스크로
├── CL-003-1: 완료 시 에스크로 정산
├── CASE-001: 잔액 부족 → 422 롤백
└── CASE-002: 중도 포기 → 부분 반환
```

`tree` 명령이 개인적으로 가장 유용하다. 헌법 조항 하나를 루트로 잡으면, 그 원칙에 의존하는 모든 법률과 판례가 트리로 표시된다. "이 원칙을 바꾸면 뭐가 영향을 받지?"가 한눈에 보인다.

---

## 성능 벤치마크

LaunchCrew 프로젝트 기준 (12 clauses, 6 case_law, 23 edges):

| 연산 | 시간 |
|------|------|
| 파싱 | 0.3ms |
| 그래프 빌드 | 0.5ms |
| 검증 (참조 + 순환 + 계층) | 0.2ms |
| 충돌 감지 | 1.1ms |
| **전체** | **2.1ms** |

규모를 키워서 테스트해봤다. 1000 clauses, 500 case_law, 3000 edges 기준:

| 연산 | 시간 |
|------|------|
| 파싱 | 5ms |
| 그래프 빌드 | 12ms |
| 검증 | 8ms |
| 충돌 감지 | 35ms |
| **전체** | **60ms** |

60ms면 IDE 플러그인에서 실시간 검증이 가능한 수준이다. TypeScript 버전은 같은 규모에서 1.2초가 걸렸다. Rust 재작성의 가치가 여기서 나온다.

---

## 아직 못 한 것

솔직히 아직 초기 단계다.

1. **의미론적 충돌 감지**: 키워드 매칭은 한계가 명확하다. LLM 연동이 필요하다.
2. **코드 연결**: `.lex` 조항과 실제 코드 파일을 연결하는 기능. `CL-001-2`가 `escrow_service.rb`의 몇 번째 줄에 구현되어 있는지 추적.
3. **실시간 검증**: 파일 워치로 `.lex` 변경 시 자동 검증. LSP(Language Server Protocol) 구현.
4. **시각화**: 의존성 그래프를 웹으로 시각화. D3.js나 Mermaid 연동.

가장 하고 싶은 건 코드 연결이다. 명세와 코드가 연결되면, "이 코드를 왜 이렇게 짰지?"에 대한 답이 항상 존재하게 된다. git blame보다 강력한 추적이 가능해진다.

---

## 정리

| 결정 | 선택 | 이유 |
|------|------|------|
| 언어 | Rust | 50x 속도, 단일 바이너리 |
| 포맷 | JSON | 파싱 편의성 (사람 친화성은 후순위) |
| 파싱 | serde | Rust 표준, 타입 안전 |
| 그래프 | HashMap + HashSet | 표준 라이브러리만 사용 |
| 순환 감지 | DFS | 표준 알고리즘 |
| 충돌 감지 | 키워드 매칭 | 초기 구현, LLM 전환 예정 |
| CLI | clap | Rust CLI 표준 |

CanonCode의 가치는 엔진의 기술적 정교함이 아니라, "명세를 코드보다 상위에 둔다"는 개발 방식에 있다. 엔진은 그 방식을 실행 가능하게 만드는 도구일 뿐이다. 도구가 완벽하지 않아도 방식 자체는 이미 가치가 있다.
