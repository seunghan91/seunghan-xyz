---
title: "Tauri 데스크톱 앱에 LaTeX 수식 달기 — KaTeX 버리고 pulldown-latex + MathML 선택한 이유"
date: 2026-04-17T09:00:00+09:00
draft: false
tags: ["tauri", "rust", "latex", "mathml", "sveltekit"]
description: "오프라인 마크다운 뷰어에 LaTeX 수식을 붙일 때 KaTeX가 정답처럼 보이지만 아니었다. pulldown-latex로 Rust에서 MathML을 찍고 WebView 네이티브 렌더에 맡기는 경로를 택한 과정."
---

오픈소스로 공개해둔 HWP/HWPX → Markdown 변환기 MDM([seunghan91/markdown-media](https://github.com/seunghan91/markdown-media))에 Tauri 데스크톱 뷰어를 붙여서 쓰고 있다. 0.3.0에서 HWPX 파서가 수식을 `$...$` / `$$...$$` LaTeX로 뽑도록 바꿨는데, 정작 뷰어에서는 달러 기호가 그대로 문자로 보였다. 수식 렌더링이 빠진 거다.

고치는 건 단순해 보였다. 마크다운 뷰어에 KaTeX 붙이면 끝. Obsidian, Typora, Zettlr 전부 이렇게 한다. 그런데 막상 조사해보니 2026년 기준 Tauri 같은 데스크톱 앱에서는 더 좋은 경로가 있었다. Rust 한 곳만 만지고 JS/CSS/폰트 번들은 0으로 유지하는 방법. 이 글은 그 선택 과정과, 덤으로 rhwp 프로젝트에 테스트 하네스를 기여하게 된 이야기다.

## 문제의 시작: 파서는 생성하는데 뷰어는 못 본다

0.3.0에서 HWPX 파서가 `<hp:equation>` 요소를 찾아서 LaTeX로 변환하도록 바꿨다. Hancom의 수식 스크립트는 LaTeX와 거의 호환되니까 그대로 `$...$` 블록에 넣으면 된다. Golden-file 테스트도 통과했다.

```rust
// core/src/hwpx/parser.rs:1102
fn extract_equation_markdown(inner: &str) -> Option<String> {
    // ... <hp:script>...</hp:script> 추출 ...
    if trimmed.contains('\n') {
        Some(format!("\n\n$$\n{}\n$$\n\n", trimmed))
    } else {
        Some(format!(" ${}$ ", trimmed))
    }
}
```

그런데 데스크톱 뷰어에서 변환된 마크다운을 열어봤더니 이렇게 나왔다.

```
피타고라스: $a^2 + b^2 = c^2$ 이다.
```

달러 기호가 그대로 문자로 보인다. 렌더링이 전혀 안 된 거다.

뷰어 쪽을 까 봤다. 마크다운 → HTML 변환은 Rust 백엔드의 `pulldown-cmark` 0.12로 한다.

```rust
// desktop/src-tauri/src/markdown.rs (수정 전)
pub fn render_markdown_to_html(markdown: &str) -> String {
    let mut options = Options::empty();
    options.insert(Options::ENABLE_TABLES);
    options.insert(Options::ENABLE_STRIKETHROUGH);
    options.insert(Options::ENABLE_TASKLISTS);

    let parser = Parser::new_ext(markdown, options);
    let mut html_output = String::new();
    html::push_html(&mut html_output, parser);
    html_output
}
```

`ENABLE_MATH` 옵션이 빠져 있다. 그래서 달러 기호가 그냥 텍스트로 흘러서 HTML에 박힌다. `{@html}`로 주입하니 수식이 있을 자리에 달러만 덩그러니 남는 거다.

켜 보면 어떻게 되나 확인해봤다.

```rust
let mut opts = Options::empty();
opts.insert(Options::ENABLE_MATH);
let parser = Parser::new_ext(md, opts);
// 결과:
// <p>inline: <span class="math math-inline">a^2+b^2=c^2</span> ...</p>
```

`<span class="math">`로 감싸주기만 한다. 실제 수식은 안 그려진다. 브라우저에 KaTeX나 MathJax가 있어야 이걸 받아서 렌더한다.

## 첫 번째 가설: KaTeX 붙이면 될 것 같다

이쯤에서 보통 KaTeX를 선택한다. Obsidian, Typora, Zettlr 모두 그렇다. npm에서 `katex` 가져와서 `+layout.svelte`에 CSS import 한 줄 추가하고, 렌더된 DOM에 `renderMathInElement()` 돌리면 끝이다. Perplexity로 빠르게 확인해봤다.

> **KaTeX vs MathJax 선택 기준 (데스크톱 오프라인 필수)**
> KaTeX 선택. KaTeX는 번들 크기 작음 (MathJax의 1/6), 렌더링 속도 5-10배 빠름, 완전 오프라인 (fonts/CSS 포함 번들 가능). 2026 기준 KaTeX v0.16+가 표준.

그래, KaTeX 쓰자. 그런데 이 답이 찜찜했다. 오프라인 데스크톱 앱인데, 브라우저 네이티브 MathML이 있는데 왜 JS 번들을 늘려야 할까? Tauri WebView는 WebKit(macOS) / WebView2(Windows)다. 둘 다 MathML 네이티브 지원 꽤 오래됐다.

더 깊이 파봤다. Perplexity에 "2026년 기준 SvelteKit + Tauri 2 오프라인에서 LaTeX 수식 렌더링, 렌더 엔진·Rust 크레이트·Svelte 래퍼·실제 성공 사례 전부" 같은 질문을 던졌다.

## 두 번째 가설: pulldown-latex + MathML로 Rust 한 곳에서

조사 결과에서 흥미로운 게 나왔다. [pulldown-latex](https://docs.rs/pulldown-latex)라는 Rust 크레이트. pulldown-cmark 저자 권이 만든 자매 크레이트다. LaTeX → **MathML** 직접 변환. KaTeX의 95% 호환. 2026년에 활발히 개발 중.

무슨 뜻이냐면, 이렇게 된다.

```
$...$ / $$...$$  (파서가 이미 생성)
    ↓
pulldown-cmark ENABLE_MATH  →  pulldown-latex  →  <math>...</math>
    ↓
Tauri WebKit / WebView2 가 네이티브 렌더
```

KaTeX JS 안 쓴다. MathJax도 안 쓴다. `<math>` 태그가 HTML에 직접 들어 있고, 브라우저가 그걸 그냥 그린다. 2020년대 초반엔 MathML 브라우저 구현이 들쭉날쭉이었는데, 2024-2026 사이에 WebKit/Chromium 모두 안정화됐다.

비교표를 뽑아봤다.

| 측정 | KaTeX 0.16+ | MathJax 3 | pulldown-latex (MathML) |
|---|---|---|---|
| gzip 크기 | 69KB JS + 폰트 ~300KB | 100-120KB + 폰트 | **0** (Rust에 컴파일) |
| 1000 수식 렌더 | 50-100ms | 200-300ms | 브라우저 네이티브 |
| 커버리지 | 85-90% | 95%+ | ~95% (KaTeX 호환) |
| 의존성 계층 | JS + CSS + 폰트 | JS + 폰트 | Rust 한 곳만 |

JS 번들이 0이라는 점이 컸다. MDM 데스크톱은 이미 Tauri 앱이라 Rust 바이너리는 있다. 거기에 크레이트 하나 더 얹는 건 빌드타임 비용만 있을 뿐 런타임·배포 비용은 없다. 반면 KaTeX는 69KB JS + 300KB 폰트 + CSS를 번들에 추가해야 하고, 뷰어 Svelte 파일에도 `renderMathInElement` 호출 로직을 붙여야 한다.

이 경로를 확정하기 전에 POC를 찍었다.

```rust
// /tmp/pulldown_latex_poc/src/main.rs
use pulldown_latex::{mathml::push_mathml, Parser as LxParser, Storage, config::RenderConfig};

let storage = Storage::new();
let parser = LxParser::new(r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", &storage);
let mut out = String::new();
push_mathml(&mut out, parser, RenderConfig::default()).unwrap();
println!("{}", out);
```

찍어봤더니 이렇게 나온다.

```html
<math display="inline">
  <mfrac>
    <mrow>
      <mi>−</mi><mi>b</mi><mo>±</mo>
      <msqrt><mrow><msup><mi>b</mi><mn>2</mn></msup><mo>−</mo><mn>4</mn><mi>a</mi><mi>c</mi></mrow></msqrt>
    </mrow>
    <mrow><mn>2</mn><mi>a</mi></mrow>
  </mfrac>
</math>
```

완벽하다. 분수, 제곱근, 위첨자 전부 MathML로 들어간다. 결정적으로, `<annotation encoding="application/x-tex">`로 감싸면 원본 LaTeX도 같이 들어간다. 복사하거나 다른 마크다운으로 다시 추출할 때 라운드트립이 된다.

## pulldown-cmark와 연결하기

POC는 LaTeX 한 줄만 넣었지만, 실제로는 마크다운 전체를 처리해야 한다. pulldown-cmark의 이벤트 스트림을 가로채서 math 이벤트만 MathML로 바꿔치는 구조.

```rust
// desktop/src-tauri/src/markdown.rs (수정 후)
use pulldown_cmark::{html, Event, Options, Parser};
use pulldown_latex::{
    config::{DisplayMode, RenderConfig},
    mathml::push_mathml,
    Parser as LatexParser, Storage,
};

pub fn render_markdown_to_html(markdown: &str) -> String {
    let mut options = Options::empty();
    options.insert(Options::ENABLE_TABLES);
    options.insert(Options::ENABLE_STRIKETHROUGH);
    options.insert(Options::ENABLE_TASKLISTS);
    options.insert(Options::ENABLE_MATH);

    let parser = Parser::new_ext(markdown, options).map(|event| match event {
        Event::InlineMath(src) => Event::InlineHtml(render_latex_to_mathml(&src, false).into()),
        Event::DisplayMath(src) => Event::InlineHtml(render_latex_to_mathml(&src, true).into()),
        other => other,
    });

    let mut html_output = String::new();
    html::push_html(&mut html_output, parser);
    html_output
}

fn render_latex_to_mathml(src: &str, display: bool) -> String {
    let storage = Storage::new();
    let parser = LatexParser::new(src, &storage);
    let mut cfg = RenderConfig::default();
    cfg.display_mode = if display { DisplayMode::Block } else { DisplayMode::Inline };
    cfg.annotation = Some(src);
    let mut out = String::new();
    match push_mathml(&mut out, parser, cfg) {
        Ok(()) => out,
        Err(_) => format!("<code class=\"math-error\">{}</code>", escape_html(src)),
    }
}
```

핵심은 `.map()` 한 줄이다. pulldown-cmark가 뱉은 이벤트 스트림을 지나가면서 `Event::InlineMath`·`Event::DisplayMath`만 pulldown-latex가 생성한 MathML `Event::InlineHtml`로 바꾼다. 나머지 이벤트는 원본 그대로 통과. 그걸 `push_html`에 넘기면 최종 HTML이 나온다.

에러 케이스를 빠뜨리면 안 된다. `\frac`에 인자를 안 넘기거나 잘못된 LaTeX이면 pulldown-latex가 Err를 뱉는다. 이걸 패닉 없이 `<code class="math-error">`로 폴백해야 원문이라도 보존된다. 수식 하나 잘못 써서 뷰어가 터지면 안 되니까.

테스트 4건 붙였다. 인라인, 블록, 잘못된 LaTeX, 수식 없는 마크다운. 전부 통과.

```rust
#[test]
fn inline_math_renders_mathml() {
    let html = render_markdown_to_html("피타고라스: $a^2 + b^2 = c^2$ 이다.");
    assert!(html.contains("<math display=\"inline\""));
    assert!(html.contains("<msup>"));
    assert!(html.contains("application/x-tex"));
}
```

빌드 통과, Svelte typecheck도 통과. 샘플 HTML을 Safari에서 열어서 눈으로 확인했더니 분수·합·적분·행렬·그리스 문자·첨자 전부 제대로 렌더됐다.

## 파급 효과: HTML 내보내기도 같이 해결됨

설계상 덤으로 해결된 게 있다. HTML export 기능.

뷰어에는 "HTML로 저장" 버튼이 있다. 예전 코드는 이랬다.

```typescript
// desktop/src/lib/components/ViewerActions.svelte
case 'html': {
  const full = `<!doctype html><meta charset="utf-8"><title>${base}</title>${data.html}`;
  downloadBlob(full, `${base}.html`, 'text/html');
  break;
}
```

`data.html`은 Rust가 만든 HTML 문자열이다. 이제 거기에 `<math>` 태그가 들어 있다. 내보낸 HTML을 Tauri 밖의 Chrome/Safari/Firefox에서 열면 그대로 수식이 보인다. KaTeX CSS를 인라인할 필요도, 폰트를 같이 묶을 필요도 없다. 브라우저가 다 한다.

KaTeX 경로를 선택했으면 이게 복잡해진다. 내보내는 HTML마다 `<link rel="stylesheet" href="...">`를 인라인하거나, 빌드타임에 `katex.renderToString()`으로 `.math` span들을 `<span class="katex">...</span>`로 미리 치환해야 한다. CSS도 인라인해야 하고, 폰트는 base64로 끼워넣거나 포기하거나 선택해야 한다. MathML 경로는 그냥 복사 붙여넣기만 해도 된다.

데스크톱 뷰어의 CSS에는 블록 수식 센터링 정도만 추가했다. KaTeX처럼 거대한 스타일시트가 필요 없다.

```css
.rendered-pane :global(math[display='block']) {
  display: block;
  margin: var(--space-4) 0;
  text-align: center;
  font-size: 1.2em;
  overflow-x: auto;
}
.rendered-pane :global(.math-error) {
  color: var(--color-error);
  background: var(--color-fill-quaternary);
  padding: 0 var(--space-1);
  border-radius: 3px;
}
```

Cargo.toml 변경은 한 줄.

```toml
pulldown-latex = "0.7"
```

이게 전부다. 버전 0.3.1로 올리고 DMG 빌드해서 [desktop-v0.3.1 릴리즈](https://github.com/seunghan91/mdm-desktop/releases/tag/desktop-v0.3.1) 올렸다.

## 알려진 한계

정직하게 몇 가지는 남았다.

- **DOCX/PDF/HWPX 내보내기**: 이 경로는 별도 Rust 모듈(`md_to_docx.rs`, `md_to_pdf.rs`)에서 처리하는데 수식 변환 로직이 없다. MathML을 DOCX의 OMML로, PDF의 네이티브 수식으로 옮기려면 각각 별도 작업이다. 별도 RFC로 빼놨다.
- **Fidelity 뷰**: MDM에는 rhwp 에디터 iframe을 띄우는 원본 충실도 뷰가 있다. 이건 HWP native equation script를 rhwp 자체 SVG 렌더러로 그린다. 마크다운 경로와 무관. 안 건드린다.
- **MathML 브라우저 차이**: 2026년 기준 Chromium/WebKit은 괜찮은데 일부 엣지 케이스에서 렌더 미세차이가 있다. 큰 문제는 아니고, Tauri WebView는 두 엔진만 타기 때문에 실제 사용자 환경에선 거의 드러나지 않는다.

## 덤: rhwp에 테스트 하네스 기여

수식 관련 작업을 하다 보니 MDM이 벤더링한 [rhwp](https://github.com/edwardkim/rhwp) 프로젝트의 이슈 트래커를 뒤져봤다. 내가 예전에 열어뒀던 [#173 이슈](https://github.com/edwardkim/rhwp/issues/173)가 눈에 띄었다.

> **HWPX 검증: rhwp SVG 스냅샷 기반 (CI에서 한컴 의존 제거)**
> Task #164의 `tools/verify_hwpx.py`는 Windows + 한컴오피스 + pyhwpx 필요해 GitHub Actions CI에서 사용 불가. rhwp 자체의 `export-svg` 명령으로 HWPX 출력의 SVG 스냅샷을 생성하고, 골든 SVG와 비교하여 회귀 검출.

MDM에서 이미 비슷한 걸 만들어뒀다. `core/tests/golden_hwpx.rs` — HWPX 파싱 결과를 골든 마크다운과 diff하는 Rust 통합 테스트. `UPDATE_GOLDEN=1`로 재생성하는 패턴. 이걸 rhwp에 그대로 이식할 수 있을 것 같았다.

rhwp를 clone해서 작업 브랜치를 만들고, 결정론 체크부터 했다.

```bash
./target/release/rhwp export-svg "samples/hwpx/form-002.hwpx" -o /tmp/a -p 0
./target/release/rhwp export-svg "samples/hwpx/form-002.hwpx" -o /tmp/b -p 0
diff -q /tmp/a /tmp/b
# (empty output = byte-identical)
```

두 번 렌더한 SVG가 바이트 단위로 일치한다. 결정론 OK. 폰트 임베딩이 꺼져 있어서 호스트 시스템 폰트가 스며들지도 않는다.

테스트 하네스는 MDM의 `golden_hwpx.rs`와 같은 구조로 짰다.

```rust
// tests/svg_snapshot.rs
fn check_snapshot(hwpx_relpath: &str, page: u32, golden_name: &str) {
    let bytes = fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(hwpx_relpath)).unwrap();
    let doc = rhwp::wasm_api::HwpDocument::from_bytes(&bytes).unwrap();
    let actual = doc.render_page_svg_native(page).unwrap();

    let golden_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/golden_svg").join(format!("{golden_name}.svg"));

    if std::env::var("UPDATE_GOLDEN").as_deref() == Ok("1") {
        fs::write(&golden_path, &actual).unwrap();
        return;
    }

    let expected = fs::read_to_string(&golden_path).unwrap();
    if actual != expected {
        let actual_path = golden_path.with_extension("actual.svg");
        let _ = fs::write(&actual_path, &actual);
        panic!("SVG snapshot mismatch for {}", golden_name);
    }
}
```

추가로 결정론 probe 테스트를 하나 더 붙였다. 같은 프로세스 안에서 두 번 렌더하고 바이트 단위로 비교. 이게 깨지면 스냅샷 테스트 자체가 신뢰할 수 없다는 신호다.

```rust
#[test]
fn render_is_deterministic_within_process() {
    let doc = rhwp::wasm_api::HwpDocument::from_bytes(&bytes).unwrap();
    let a = doc.render_page_svg_native(0).unwrap();
    let b = doc.render_page_svg_native(0).unwrap();
    assert_eq!(a, b, "render_page_svg_native must be deterministic");
}
```

골든 생성하고 테스트 두 번 돌렸다. 전부 통과. rhwp의 기존 `cargo test` CI 잡에 자동으로 붙어서 돌아간다. 별도 workflow 추가 없이. 별도 Windows 러너도 없이. 별도 Hancom Office 설치도 없이.

[PR #181](https://github.com/edwardkim/rhwp/pull/181)로 올렸다. 나중에 머지되면 rhwp가 수식 레이아웃 엔진을 손볼 때마다 이 스냅샷이 회귀를 잡아준다.

## 정리

Tauri 데스크톱 앱에서 LaTeX 수식을 렌더할 때 2026년 현재 가장 깔끔한 경로는 이거다.

- **Rust 쪽**: pulldown-cmark `ENABLE_MATH` 켜고, math 이벤트를 pulldown-latex로 가로채서 MathML로 변환.
- **프론트엔드 쪽**: 손 안 댐. WebView가 MathML을 네이티브로 그린다.
- **내보내기**: 자동 지원. `<math>` 태그가 이미 HTML에 들어 있다.

KaTeX를 붙이는 업계 표준 경로는 여전히 유효하지만, 오프라인 데스크톱 앱이면 번들 크기와 계층 복잡도 면에서 MathML 경로가 낫다. `pulldown-latex`가 KaTeX 95% 호환이라 커버리지도 충분하다.

전체 커밋 하나, 버전 0.3.1로 릴리즈, 그리고 덤으로 rhwp 프로젝트에 PR 하나. 오픈소스 프로젝트끼리 서로 기여가 물려들어가는 건 항상 기분 좋다.

참고 링크:

- MDM 메인 저장소: [seunghan91/markdown-media](https://github.com/seunghan91/markdown-media)
- MDM 데스크톱 릴리즈: [mdm-desktop v0.3.1](https://github.com/seunghan91/mdm-desktop/releases/tag/desktop-v0.3.1)
- rhwp 프로젝트: [edwardkim/rhwp](https://github.com/edwardkim/rhwp)
- 기여 PR: [rhwp#181](https://github.com/edwardkim/rhwp/pull/181) (closes [#173](https://github.com/edwardkim/rhwp/issues/173))
- pulldown-latex: [docs.rs/pulldown-latex](https://docs.rs/pulldown-latex)
