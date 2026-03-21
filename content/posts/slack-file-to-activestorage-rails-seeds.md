---
title: "Slack 파일을 Rails 프로젝트에 반영하기 — URL 저장이 아닌 소스 포함"
date: 2026-03-12
draft: false
tags: ["Rails", "ActiveStorage", "Slack API", "Seeds", "삽질"]
description: "Slack 채널에 올라온 HTML 파일을 Rails 앱에서 보여줘야 했다. slack-files.com URL을 저장하면 끝일 줄 알았는데, 외부에서 접근이 안 됐다. 삽질 과정과 최종 해결 방법을 정리한다."
cover:
  image: "/images/og/slack-file-to-activestorage-rails-seeds.png"
  alt: "Slack File To Activestorage Rails Seeds"
  hidden: true
categories: ["Rails"]
---

팀원들이 Slack 채널에 HTML 파일을 과제로 제출하고 있었다. Rails 앱의 제출 상세 페이지에서 이 파일들을 인라인으로 미리보기할 수 있게 만들어야 했다. "URL 저장하면 되겠지"라는 생각으로 시작했다가 세 번의 방향 전환을 거쳤다.

---

## 1차 시도: Slack 파일 URL을 그대로 seeds에 저장

Slack의 파일 공유 URL은 이런 형태다:

```
https://slack-files.com/T0xxx-F0xxx-hash
```

이걸 seeds.rb에 넣고 `SlackFileImporter`로 다운로드하면 ActiveStorage에 자동 첨부되는 구조가 이미 있었다.

```ruby
SlackFileImporter.new(submission, slack_url).call
```

**문제:** `SlackFileImporter`는 내부적으로 `SLACK_BOT_TOKEN` 환경변수를 사용한다. 배포 환경에는 토큰이 있지만, **seeds가 실행되는 시점에 Slack API 호출이 실패하면 파일이 누락**된다. 그리고 근본적으로 slack-files.com URL은 인증 없이 외부 웹에서 접근이 안 된다.

---

## 2차 시도: iframe에서 Slack URL 직접 참조

"ActiveStorage에 저장 안 해도 iframe src에 URL 넣으면 되지 않나?"

```erb
<iframe src="https://slack-files.com/T0xxx-F0xxx-hash"></iframe>
```

당연히 안 된다. Slack 파일 URL은 **인증된 세션에서만 접근 가능**하다. 일반 브라우저에서 열면 404 또는 로그인 페이지로 리다이렉트된다.

---

## 최종 해결: 파일을 프로젝트 소스에 직접 포함

결국 파일 내용 자체를 프로젝트에 넣어야 한다. 전체 플로우는 이렇다:

### Step 1: Slack 채널 아카이브에서 file ID 확인

Slack 채널을 아카이브해둔 마크다운 파일에서 파일 정보를 찾는다.

```markdown
**첨부 파일:**
- vienna-trip.html (HTML, 22.5KB)
  - URL: https://slack-files.com/T0xxx-F0ALD478D1N-hash
```

URL 중간의 `F0ALD478D1N`이 **Slack file ID**다.

### Step 2: 서버에서 Slack API로 파일 다운로드

로컬에는 Slack 토큰이 없으므로, 배포 서버에서 Rails runner로 실행한다.

```bash
ssh your-server "cd /app && bin/rails runner \"
  require 'net/http'; require 'json'; require 'uri'
  token = ENV['SLACK_BOT_TOKEN']
  file_id = 'F0ALD478D1N'

  # files.info API로 다운로드 URL 획득
  uri = URI('https://slack.com/api/files.info')
  uri.query = URI.encode_www_form(file: file_id)
  req = Net::HTTP::Get.new(uri)
  req['Authorization'] = 'Bearer ' + token
  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(req) }
  data = JSON.parse(res.body)

  # 실제 파일 다운로드
  dl_uri = URI(data['file']['url_private_download'])
  dl_req = Net::HTTP::Get.new(dl_uri)
  dl_req['Authorization'] = 'Bearer ' + token
  content = Net::HTTP.start(dl_uri.hostname, dl_uri.port, use_ssl: true) do |http|
    http.request(dl_req)
  end.body

  puts content
\""
```

여러 파일을 한 번에 받을 때는 구분자를 넣어 출력하고 로컬에서 split한다.

### Step 3: 프로젝트 소스에 저장

```
public/submissions/user_folder/vienna-trip.html
public/submissions/user_folder/travel-taste-finder.html
```

git에 포함되어 배포 시 함께 올라간다.

### Step 4: seeds.rb에서 ActiveStorage로 attach

```ruby
user = User.find_by(name: "제출자")
sub = Submission.find_by(assignment: assignment, user: user)

{
  "vienna-trip.html"         => "text/html",
  "travel-taste-finder.html" => "text/html"
}.each do |filename, content_type|
  unless sub.files.any? { |f| f.filename.to_s == filename }
    path = Rails.root.join("public", "submissions", "user_folder", filename)
    if File.exist?(path)
      sub.files.attach(
        io: File.open(path),
        filename: filename,
        content_type: content_type
      )
    end
  end
end
```

핵심은 `SlackFileImporter`를 쓰지 않고 **`File.open`으로 로컬 파일을 직접 attach**하는 것이다. Slack API 의존성이 사라진다.

---

## HTML 파일 인라인 미리보기 구현

파일이 ActiveStorage에 들어가면, 제출 상세 페이지에서 보여줘야 한다. 기존에 PDF, 이미지, 마크다운, DOCX 미리보기는 있었지만 HTML은 없었다.

### 파일 타입 감지

```erb
<% is_html = ct.include?("html") || file.filename.to_s.end_with?(".html", ".htm") %>
```

### 아코디언 토글 버튼 + iframe

```erb
<% if is_html %>
  <button onclick="toggleHtmlPreview('<%= preview_id %>', '<%= toggle_id %>')">
    <%= file.filename %> 미리보기
  </button>

  <div id="<%= preview_id %>" style="display: none;">
    <iframe
      src="<%= rails_blob_path(file, disposition: 'inline') %>"
      sandbox="allow-same-origin"
      loading="lazy"
      onload="try { var h = this.contentDocument.body.scrollHeight;
        if (h > 600) this.style.height = Math.min(h + 40, 2000) + 'px';
      } catch(e) {}"
    ></iframe>
  </div>
<% end %>
```

여러 HTML 파일이 있을 때 **아코디언 방식**으로 하나를 열면 다른 건 자동으로 닫힌다:

```javascript
function toggleHtmlPreview(previewId, toggleId) {
  var preview = document.getElementById(previewId);
  var isOpening = preview.style.display === 'none';

  // 다른 열린 패널 모두 닫기
  if (isOpening) {
    document.querySelectorAll('.html-preview-panel').forEach(function(panel) {
      if (panel.id !== previewId) {
        panel.style.display = 'none';
      }
    });
  }

  preview.style.display = isOpening ? 'block' : 'none';
  if (isOpening) {
    preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}
```

### sandbox 속성

`sandbox="allow-same-origin"`으로 제한해서 첨부된 HTML이 부모 페이지의 DOM을 조작하거나 스크립트를 실행하지 못하게 한다.

---

## 삽질에서 배운 것

1. **Slack 파일 URL은 외부 접근 불가** — 인증 없이는 404. URL을 DB에 저장하는 건 의미 없다.
2. **SlackFileImporter 의존을 끊어라** — seeds에서 Slack API를 호출하면 토큰 만료, 네트워크 문제 등으로 불안정하다. 파일을 소스에 포함시키면 확실하다.
3. **content_type을 명시하라** — ActiveStorage의 `attach`에서 `content_type: "text/html"`을 빼먹으면 `application/octet-stream`으로 저장되어 iframe에서 렌더링이 안 된다.
4. **iframe sandbox는 필수** — 사용자가 올린 HTML을 그대로 렌더링하면 XSS 위험이 있다. `sandbox` 속성으로 제한하되, 스타일과 레이아웃이 정상 동작하려면 `allow-same-origin`은 필요하다.

---

## 최종 구조

```
project/
├── public/submissions/
│   └── user_folder/
│       ├── vienna-trip.html          # Slack에서 받은 원본
│       └── travel-taste-finder.html
├── db/seeds.rb                       # File.open으로 직접 attach
└── app/views/submissions/show.html.erb  # 아코디언 HTML 미리보기
```

Slack URL을 저장하는 대신 파일 자체를 소스에 포함하니, 외부 서비스 의존 없이 안정적으로 동작한다.
