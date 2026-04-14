---
title: "HWP 변환기를 MCP 툴로 만들기 — 기존 Gateway에 3줄 추가하는 법"
date: 2026-04-15T09:00:00+09:00
draft: false
tags: ["MCP", "Rust", "HWP", "Claude", "AI Agent"]
description: "독립 MCP 서버를 만드는 대신 기존 Korea Law Hub Gateway에 MDM 변환 툴 3개를 추가했다. 인증·rate limit·로깅을 그대로 재사용하는 통합 전략과 Rust 바이너리 stdin/stdout 모드 설계 기록."
---

오픈소스로 만든 Rust 문서 변환기 MDM(Markdown-Media)을 AI agent에서 직접 호출할 수 있게 MCP 서버로 노출하는 작업을 했다. 처음엔 `@mdm/mcp-server` 독립 Node.js 패키지로 만들 생각이었는데, 이미 운영 중인 Korea Law Hub Gateway에 tool 3개 추가하는 쪽이 훨씬 낫다는 결론이 나왔다.

이 글은 그 판단 과정과 실제 구현에서 걸린 지점들을 정리한다.

## 상황

MDM은 HWP, HWPX, PDF, DOCX, PPTX, XLSX, HTML, CSV, TXT를 Markdown으로 바꾸는 Rust 변환기다. 데스크톱 앱, PyPI 패키지(`pip install mdm-parser`), CLI 바이너리는 이미 있었다. 남은 건 Claude Code, Cursor, Continue.dev 같은 AI agent에서 MCP 프로토콜로 직접 부르는 경로.

마침 법률 문서 검색 서비스 Korea Law Hub가 있었다. 여기엔 이미 법제처 API 44개를 MCP tool로 래핑한 Gateway가 `law-check.com/api/mcp`에서 돌고 있었다. 인증(`UserMcpKey`), rate limit(`cost_units`), 사용량 로깅, SSE 전송 전부 구축돼 있는 상태.

## 처음엔 독립 서버를 고민했다

첫 안은 `@mdm/mcp-server` 라는 Node.js 패키지였다.

- `@modelcontextprotocol/sdk-typescript`로 stdio/HTTP 양쪽 지원
- Rust 바이너리를 subprocess로 호출
- Docker 이미지 + npm 배포 → 사용자가 로컬에서 띄우는 구조

장점은 law 프로젝트와 완전히 분리된다는 것. 단점이 컸다:

- 인증·키 관리 로직을 처음부터 또 짜야 함
- rate limit 없으면 문서 한 개에 수초 걸리는 변환이 DoS 벡터가 됨
- 사용량 로깅, 과금 인프라 또 만들어야 함
- 사용자 입장에서 MCP 키 2개 관리 (법률 검색용 + 문서 변환용)

## 통합을 선택한 이유

Korea Law Hub Gateway 코드를 읽어보니 `TOOL_PERMISSION_MAP`, `TOOL_COST`, `CONSOLIDATED_TOOL_NAMES` 이 3개 상수에 tool 추가하고 `proxy_to_mcp_server`에 분기만 추가하면 끝이었다. 기존 미들웨어가 인증·로깅·rate limit을 다 해주니 내가 쓸 건 300줄 정도의 dispatcher 로직뿐.

사용자 흐름도 자연스러워진다.

```
계약서.hwp → mdm_convert_document (파싱)
          → search_legal_es (관련 법령 검색)
          → compare_amendment (개정 이력)
          → LLM 종합
```

카테고리도 겹치지 않는다. MDM은 "사용자 제공 문서 파싱", Hub 기존 tool은 "법제처 DB 조회". 한 Gateway 안에 있어도 역할이 깔끔히 분리된다.

## Tool 3개 설계

MCP tool 설계할 때 찾아보니 2026년 현재 통용되는 컨벤션이 명확하다.

| 원칙 | 반영 |
|------|------|
| snake_case + verb_object | `mdm_convert_document`, `mdm_extract_text` |
| 네임스페이스 prefix | `mdm_*` — 법률 tool과 명확히 구분 |
| 파일 전달은 URL 우선 | `file_url` 선호, `file_base64`는 5MB 상한 |
| 플랫 스키마 | 중첩 없이 `file_url`, `filename`, `mode` 평면 |

결과적으로 3개 tool을 노출했다.

```ruby
"mdm_convert_document" => 6,   # cost units (CPU 가중치)
"mdm_extract_text"     => 3,
"mdm_detect_format"    => 1
```

`mdm_detect_format`는 변환 실행 없이 확장자·매직바이트로만 판정한다. 비싼 tool 호출 전에 미리 체크할 때 쓰라고 분리했다.

## Rust 바이너리에 stdin/stdout 모드 추가

Gateway에서 MDM을 부를 때 임시 파일 왕복이 불편했다. Rails에서 `Tempfile.create` 후 바이너리에 경로 전달, 바이너리가 다시 결과를 디스크에 쓰고 Rails가 다시 읽는 구조.

`stream` 서브커맨드를 추가해 stdin/stdout 파이프로 동작하게 바꿨다.

```rust
Stream {
    #[arg(long)]
    ext: String,

    #[arg(long, default_value = "mdx")]
    mode: String,
}
```

내부적으로는 여전히 tempdir을 쓴다. HWP는 OLE 랜덤 액세스가 필요하고 PDF도 seek이 필요해서 파일 기반 파서를 그대로 재사용하는 게 맞았다. 다만 외부 인터페이스는 순수 파이프.

문제는 `convert_file`이 내부적으로 `println!("📄 Converting: ...")` 같은 상태 메시지를 찍는다는 점. 이걸 stdout에 그대로 섞으면 Markdown 파싱이 깨진다.

해결은 Unix fd 리다이렉션 RAII 가드:

```rust
#[cfg(unix)]
struct StdoutSilencer { saved_fd: libc::c_int }

impl StdoutSilencer {
    fn new() -> io::Result<Self> {
        let saved_fd = unsafe { libc::dup(libc::STDOUT_FILENO) };
        let devnull = fs::File::create("/dev/null")?;
        unsafe { libc::dup2(devnull.as_raw_fd(), libc::STDOUT_FILENO) };
        Ok(Self { saved_fd })
    }
}

impl Drop for StdoutSilencer {
    fn drop(&mut self) {
        let _ = io::stdout().flush();
        unsafe {
            libc::dup2(self.saved_fd, libc::STDOUT_FILENO);
            libc::close(self.saved_fd);
        }
    }
}
```

`convert_file` 호출 직전에 가드를 띄워 stdout을 /dev/null로 리다이렉트, 변환이 끝나면 Drop으로 복구. 복구 직전에 `flush()`를 반드시 호출해야 한다. 안 그러면 버퍼에 남은 상태 메시지가 복구된 stdout으로 흘러나와 Markdown 페이로드를 오염시킨다.

실제로 이 flush 없이 돌렸을 때 `---\nformat: pdf\n...` 대신 `📄 Converting: input.pdf\n---\n...`가 나와서 1분 헤맸다.

## frontmatter 스트립

MDM은 기본적으로 YAML frontmatter 포함 출력이다.

```
---
format: pdf
source: "input.pdf"
pages: 5
---

# Main Title

본문...
```

LLM에 넘길 땐 본문만 필요한 경우가 많다. `--mode body` 옵션으로 frontmatter 제거 기능을 추가했다.

```rust
fn strip_frontmatter(s: &str) -> String {
    if !s.starts_with("---\n") { return s.to_string(); }
    if let Some(end) = s[4..].find("\n---\n") {
        let body_start = 4 + end + "\n---\n".len();
        return s[body_start..].trim_start().to_string();
    }
    s.to_string()
}
```

처음엔 `Regex`로 갔다가 `regex` crate가 스트리밍 매칭 안 되는 단순 패턴이라 byte offset 계산으로 바꿨다. 훨씬 빠르다.

## 보안 — file_url 검증

Gateway가 `file_url`을 받아 서버에서 GET하는 구조라서 SSRF가 걱정됐다. 최소한의 방어:

```ruby
unless file_url.match?(%r{\Ahttps?://}i)
  return mdm_error("file_url must be http(s)")
end
```

`file://`, `ftp://`, `gopher://` 등 전부 거부. 프로덕션에서는 여기에 private IP 대역 차단(127.0.0.0/8, 10.0.0.0/8 등)까지 추가해야 한다. 이번엔 스코프를 좁혀 프로토콜 허용 리스트만 걸었다.

`file_base64`는 5MB 상한. 더 크면 `file_url` 쓰라고 에러를 돌려준다.

```ruby
if bytes.bytesize > 5 * 1024 * 1024
  return mdm_error("file_base64 payload exceeds 5 MB — use file_url for larger files")
end
```

## data_source 구분

Gateway는 기본적으로 응답에 `data_source: "law.go.kr"`을 붙인다. 법제처 API 래핑이라서 맞는데, MDM은 사용자 제공 문서 파싱이라 이 라벨이 오해를 부른다.

```ruby
sanitized["data_source"] ||=
  if tool_name.start_with?("mdm_")
    "user_provided_document (MDM Rust engine)"
  elsif tool_name.start_with?("weknora_")
    "weknora_kb:대한민국 법령"
  else
    "law.go.kr"
  end
```

LLM이 응답을 보고 "이 변환 결과가 어디서 왔는지" 정확히 판단하도록.

## 실측 검증

Rails runner로 각 tool을 직접 호출해 확인했다.

```ruby
ctrl = Api::McpController.new
ctrl.send(:dispatch_mdm_tool, "mdm_detect_format",
          { "filename" => "계약서.hwp" })
# => {"status"=>"OK", "extension"=>"hwp", "supported"=>true, ...}

ctrl.send(:dispatch_mdm_tool, "mdm_convert_document",
          { "file_base64" => Base64.encode64(File.binread("test.html")),
            "filename" => "test.html",
            "mode" => "body" })
# => {"status"=>"OK", "format"=>"html", "elapsed_ms"=>20, "markdown"=>"# Hello...", ...}
```

DOCX 수식 문서, HTML 체크박스, PDF 헤딩 문서 전부 정상 변환. 지원 안 되는 포맷 주면 `{"status": "ERROR", ...}` 깨끗하게 반환.

## 결론

기존에 인증·로깅·rate limit이 이미 구축된 Gateway가 있다면, 새 기능을 독립 MCP 서버로 빼는 것보다 기존 Gateway에 tool을 추가하는 게 거의 항상 낫다. 사용자는 키 하나만 관리하면 되고, 개발자는 인프라 재사용하고, 카테고리만 tool prefix로 구분하면 응집도도 유지된다.

MDM 바이너리에 `stream` 서브커맨드를 추가한 건 Gateway뿐 아니라 일반 쉘 파이프라인에서도 유용하다. Docker 컨테이너, CI job, 서버 사이드 변환 전부 임시 파일 경로 고민 없이 stdin/stdout으로 연결 가능.

설정법 전체는 [MDM GETTING-STARTED.md](https://github.com/seunghan91/markdown-media/blob/master/GETTING-STARTED.md)에 정리해뒀다.
