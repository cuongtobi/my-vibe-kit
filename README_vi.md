# my-vibe-kit

[English](README.md)

Một bộ **vibe-coding skills cá nhân, gọn nhẹ** để làm việc trên repository thật với Codex, Claude Code và Google Antigravity.

Kit cố ý giữ bề mặt agent nhỏ:

- `vibe` — điều phối toàn bộ thay đổi.
- `plan` — xây context có giới hạn, phân tích dependency/impact và lập kế hoạch.
- `build` — chỉ triển khai đúng phạm vi đã được lập kế hoạch.
- `verify` — chứng minh thay đổi bằng bằng chứng runtime thực tế.

Bốn skill dùng chung được `install.py` materialize vào layout native của từng agent, vì vậy chỉ có **một nguồn sự thật** thay vì duy trì nhiều bản riêng.

## Bắt đầu nhanh

Clone kit:

```bash
git clone https://github.com/cuongtobi/my-vibe-kit.git
cd my-vibe-kit
```

Cài vào project:

```bash
python install.py --target /duong-dan/toi/project --agents codex claude antigravity
```

Windows PowerShell:

```powershell
python .\install.py --target C:\code\your-project --agents codex claude antigravity
```

Preview mà chưa ghi file:

```bash
python install.py --target /duong-dan/toi/project --agents all --dry-run
```

Sau đó mở project bằng Codex, Claude Code hoặc Antigravity và dùng bình thường:

```text
Use vibe to add tính năng export CSV cho báo cáo.
```

```text
Use vibe to fix lỗi backtest crash khi history rỗng.
```

```text
Use plan to phân tích việc đổi SQLite sang PostgreSQL. Chưa sửa code.
```

Workflow chính:

```text
vibe
  -> plan: persistent context + dependency + impact + plan
  -> build: code + test
  -> verify: dependency diff + lint/type/test/build + diff review
```

Với bug:

```text
REPRODUCE
-> ROOT CAUSE
-> FAILING REGRESSION TEST
-> MINIMAL FIX
-> PASSING REGRESSION TEST
-> AFFECTED TESTS
-> VERIFY
```

Nếu project chưa có command test/lint/typecheck/build đáng tin cậy, hãy chỉnh `.vibe/config.json`. Kit sẽ trả `NEEDS_VERIFICATION_CONFIG` thay vì tự nhận project đã verify.

## Mục tiêu thiết kế

- Một workflow cá nhân dùng chung cho Codex, Claude Code và Antigravity.
- Hoạt động với skill filesystem theo project và agent CLI/IDE.
- Context lưu bằng file thay vì phụ thuộc chat history.
- Cache JSON context/dependency bền vững qua nhiều session.
- Refresh tăng dần theo Git delta thay vì quét lại toàn repository cho mỗi task.
- Relevant-context retrieval có giới hạn và Unicode-aware trước khi model reasoning.
- Có content fallback được kiểm soát khi indexed retrieval có độ tin cậy quá thấp.
- Chọn primary stack theo task cho repository polyglot mà không làm mất lợi ích của project-level cache.
- Các mode rõ ràng: `feature`, `change`, `bug_fix`, `refactor`, `hotfix`.
- Mặc định ưu tiên thay đổi nhỏ nhất đúng yêu cầu.
- Phải có runtime evidence trước khi hoàn tất.
- Runtime của kit chỉ dùng Python standard library.
- Có thể tích hợp tool native mạnh hơn khi project đã sử dụng.

## Ngôn ngữ và framework hỗ trợ

Workflow độc lập ngôn ngữ. Runtime có stack adapter và dependency scanner baseline theo từng stack.

| Ngôn ngữ | Dependency scan baseline | Framework adapter |
| --- | --- | --- |
| Python | AST import graph | Flask, FastAPI, Django |
| JavaScript | relative + alias tsconfig/jsconfig + local npm/yarn/pnpm workspace import graph | Express, React, Vue, Nuxt, Svelte, SvelteKit, Vite, Next.js |
| TypeScript | relative + alias tsconfig/jsconfig + local npm/yarn/pnpm workspace import graph | Express, NestJS, React, Vue, Nuxt, Svelte, SvelteKit, Vite, Next.js |
| PHP | namespace/use + literal require/include graph | Laravel, WordPress |
| Java/Kotlin | package/import graph | Spring |
| Go | module-local import graph | Gin, Fiber |
| Rust | mod + `crate::use` graph | Actix Web |
| Ruby | graph `require` / `require_relative` literal | Ruby on Rails |
| Khác | project/file map | generic fallback |

Framework adapter bổ sung context như route, component, controller, model, provider và gợi ý verification riêng cho framework. Frontend adapter hiểu component, hook/composable/store, file-system route và server/client boundary. WordPress CMS adapter hiểu plugin, theme, hook/filter/shortcode, REST route, block, template và boundary tích hợp của WordPress. Rails adapter hiểu controller/model/service/job/mailer/policy theo convention, route, boundary ActiveRecord và guidance kiến trúc có tính đến Zeitwerk; dependency baseline tĩnh cố ý chỉ ghi các edge local `require` / `require_relative` explicit.

Runtime resolve:

```text
detected languages + primary language
       +
detected framework(s)
       ↓
active-adapter.json
       ↓
plan / impact / build / verify
```

`active-adapter.json` expose toàn bộ language adapter đã detect cùng `primary_language`; field `language` đơn vẫn được giữ tạm như compatibility alias cho consumer cũ. Vì vậy 4 skill cốt lõi không cần tạo bản riêng cho Flask/Laravel/Rails/React/WordPress...

Với frontend, adapter có thể merge nhiều lớp. Project TypeScript + React + Vite có thể active cả ba; project Next.js có thể active Next.js + React nhưng architecture guidance ưu tiên meta-framework. Tương tự Nuxt được ưu tiên hơn Vue và SvelteKit ưu tiên hơn Svelte. Vite chỉ là tooling adapter, không quyết định application architecture.

## Ranh giới module runtime

Runtime được tách theo trách nhiệm để tránh tiếp tục phình thành một core đơn khối:

- `vibe_core.py` — orchestration, project/dependency graph, impact, snapshot, verification.
- `vibe_retrieval.py` — Unicode tokenization, query expansion, confidence scoring, bounded fallback và relevant-context selection.
- `vibe_tasks.py` — task record cùng retention/GC lifecycle explicit.
- `vibe_stacks.py` — stack detection, task-aware stack selection, adapter và framework context.
- `vibe_state.py` — persistent cache và Git delta.
- `vibe_architecture.py` — architecture/clean-code policy đã resolve.

Public CLI/skill vẫn tập trung ở `vibe.py` và bốn skill cốt lõi.

## Chính sách kiến trúc

Với project mới, mặc định:

```text
feature-first
+
modular layered architecture
+
framework-native conventions
+
Clean Code rules
```

Profile mặc định thực tế là `standard`:

```text
presentation / route / controller
            ↓
application / service
            ↓
domain / business rules
            ↓
repository / data / infrastructure boundary
```

Đây là hướng dẫn, không phải yêu cầu tạo mọi layer cho mọi feature. Repository, interface, port, wrapper, factory và adapter chỉ được thêm khi có boundary, variation, reuse hoặc test seam thực sự cần thiết.

Kit chỉ chuyển sang dependency rule kiểu Clean/Hexagonal khi:

- đặt rõ `architecture.profile` thành `strict`, hoặc
- `profile=auto` và project vượt strict threshold đã cấu hình.

Config kiến trúc mặc định:

```json
{
  "architecture": {
    "profile": "auto",
    "default_profile": "standard",
    "module_style": "feature-first",
    "default_pattern": "modular-layered",
    "strict_pattern": "hexagonal",
    "framework_conventions": "prefer",
    "allow_auto_strict": true,
    "strict_thresholds": {
      "source_files": 300,
      "feature_roots": 20
    }
  }
}
```

Bật strict thủ công:

```json
{
  "architecture": {
    "profile": "strict"
  }
}
```

Dependency direction ở strict mode:

```text
presentation
    ↓
application / use-cases
    ↓
domain
    ↑
ports
    ↑
infrastructure adapters
```

Framework convention vẫn được ưu tiên hơn ceremony kiến trúc chung. Laravel vẫn theo Laravel, Django vẫn theo app, NestJS vẫn theo module/provider, Spring ưu tiên package-by-feature...

Policy đã resolve được materialize vào:

```text
.vibe/runtime/architecture-policy.json
```

File này chứa:

- requested/effective profile,
- pattern được chọn,
- tín hiệu kích thước project,
- lý do auto-strict,
- cấu trúc framework-native đề xuất,
- dependency-direction rules,
- Clean Code rules.

Clean Code mặc định gồm: tên rõ ý nghĩa, function/module tập trung, giảm nesting khi hợp lý, transport handler mỏng, lỗi/dependency rõ ràng, không mutable global state ẩn, không abstraction suy đoán, test theo behavior và ưu tiên code đơn giản hơn code “clever”.

## Chính sách comment và documentation

Kit coi comment là thông tin phục vụ bảo trì, không phải phần diễn giải lại code. Khi build và review, ưu tiên code tự giải thích bằng tên và cấu trúc; chỉ thêm comment khi cần giữ lại thông tin mà bản thân code không thể hiện rõ.

Nên dùng comment/docstring cho các trường hợp như:

- lý do tồn tại của một implementation hoặc tradeoff không hiển nhiên,
- business rule hoặc constraint về compatibility,
- security assumption và invariant quan trọng,
- reasoning về performance, cache, invalidation hoặc concurrency,
- thuật toán khó, edge case và workaround có chủ đích,
- contract của public/shared API khi caller cần biết behavior, side effect, error hoặc lifecycle.

Tránh comment chỉ lặp lại dòng code kế tiếp, lặp tên function/variable, giải thích cú pháp thông thường hoặc thêm docstring boilerplate cho private helper đơn giản. TODO/FIXME phải cụ thể và có thể hành động được.

Skill `build` phải cập nhật/xóa comment gần vùng sửa khi behavior đã thay đổi. Skill `verify` kiểm tra cả hai chiều: thiếu rationale ở code thực sự khó hiểu và comment thừa/sai/stale làm việc bảo trì khó hơn.

## Security Policy

Kit **không** tuyên bố hay đảm bảo code được tạo/sửa là an toàn tuyệt đối. Mục tiêu security của kit hẹp hơn và có thể audit:

> **Security-sensitive changes cannot silently pass without explicit security review/evidence.**

Workflow:

```text
PLAN
  ↓
identify security-sensitive surface
  ↓
BUILD
  ↓
secure coding rules
  ↓
VERIFY
  ├─ security diff review
  ├─ project-native security scanner nếu có
  ├─ dependency vulnerability check khi phù hợp/có sẵn
  └─ targeted security tests
```

Task được coi là `security-sensitive` khi request hoặc impact thực tế chạm vào authentication, authorization, session, token, password, file upload/filesystem, database query với dữ liệu do user kiểm soát, URL do user kiểm soát, HTML rendering, command/process execution, payment, secrets/credentials hoặc trust boundary tương đương.

Ở bước plan, kit ghi rõ trust boundary bị ảnh hưởng, input không đáng tin cậy, tài sản cần bảo vệ, abuse/failure case, security control hiện có phải giữ và evidence cần cho verify. Build áp dụng secure default native của framework cùng các control phù hợp từng surface. Verify phân loại lại từ diff cuối cùng để một thay đổi nhạy cảm không thể thoát security review chỉ vì bước plan bỏ sót.

Ví dụ với refresh token/session, review phải xét token rotation/expiry, revocation, replay risk, cookie flags, session fixation, authorization boundary và việc log token/secret. Với file upload, review phải xét giới hạn dung lượng, MIME/extension, path traversal, filename sanitization, overwrite behavior, execution risk, storage boundary và authorization.

Với task security-sensitive, lint/type/test/build pass hoặc runtime `PASS_VERIFIED` **chưa đủ** để coi task hoàn tất. Verify phải ghi một phần **Security evidence** riêng gồm security diff review, targeted test/check, kết quả scanner nếu có, dependency-vulnerability evidence khi phù hợp và các limitation còn lại. Nếu project không có scanner thì phải ghi rõ thay vì âm thầm coi là success.

## Runtime contracts và workflow completion

Runtime artifact giờ có `artifact_type` và `schema_version` rõ ràng. Validator chỉ dùng Python standard library và đọc `schemas/contracts-v1.json` làm contract manifest được commit cùng repo cho `project-map.json`, `dependency-map.json`, `relevant-context.json`, `verification.json`, task record, dependency diff, security candidate, structured evidence và completion status. Config version 1-3 vẫn đọc được để tương thích ngược, nhưng type sai hoặc version không hỗ trợ sẽ bị báo lỗi rõ ràng. Cache project/dependency không đúng contract sẽ bị rebuild thay vì được tin cậy.

`PASS_VERIFIED` được giữ để tương thích và chỉ có nghĩa các runtime check đã cấu hình pass trên source fingerprint ổn định, đồng thời không vi phạm điều kiện dependency cycle. Trạng thái hoàn tất task là gate riêng:

```text
PASS_VERIFIED
      +
mọi acceptance criterion = met
      +
security decision/evidence rõ ràng
      ↓
COMPLETE
```

Verify ghi `acceptance-evidence.json` và `security-evidence.json` qua CLI, sau đó chạy:

```bash
python .vibe/tools/vibe.py complete --summary
```

Completion gate có thể trả `COMPLETE`, `INCOMPLETE_VERIFICATION`, `INCOMPLETE_ACCEPTANCE`, `INCOMPLETE_SECURITY` hoặc `INCOMPLETE`. Security classifier của runtime chỉ là advisory: `security-candidates.json` thu tín hiệu từ request/path/content/framework route, còn agent vẫn quyết định classification cuối cùng. Nếu runtime có candidate nhưng quyết định cuối là non-sensitive thì evidence phải ghi rationale override.

Auto-strict architecture cũng trở thành task-aware. Khi retrieval đã có target rõ ràng, threshold được đánh giá trên các module liên quan tới task thay vì tự động ép cả monorepo lớn sang strict chỉ vì có nhiều source file không liên quan. `architecture-policy.json` hiển thị cả kích thước repository và task scope thực tế dùng để quyết định.

Retrieval bổ sung `selection_diagnostics` và `test_diagnostics`, giải thích file được chọn vì là target, forward dependency, reverse consumer hay test liên quan, kèm dependency depth và cạnh `via` gần nhất khi có.

## Kiến trúc persistent context

Kit không coi chat history hoặc toàn bộ task cũ là source of truth.

Nó tách 4 lớp:

```text
durable project truth
persistent local state
current-task runtime
cold task history
```

### Durable project truth

Thông tin đã commit của project vẫn là nguồn chính:

```text
AGENTS.md
.vibe/config.json
source code
tests
package manifests
architecture docs
```

### Persistent state qua nhiều session

State local tái sử dụng nằm tại:

```text
.vibe/state/
├── index-state.json
├── file-index.json
├── last-context.json
├── last-dependency.json
├── last-framework.json
├── last-adapter.json
├── last-architecture.json
└── content-hashes.json
```

`.vibe/state/` được ignore bởi `.vibe/.gitignore`.

Đây chỉ là performance cache, không phải project truth và không phải verification evidence.

`index-state.json` lưu version schema/scanner, checksum SHA-256 của artifact và Git repository state tương ứng với cache. Toàn bộ context bundle (file index, context, framework, adapter, architecture) và dependency cache được kiểm tra trước khi tái sử dụng hoặc refresh incremental. Artifact thiếu, hỏng hoặc không nhất quán sẽ kích hoạt full rebuild; repository rỗng hợp lệ vẫn được cache.

`file-index.json` đồng thời lưu search index có giới hạn cho source: symbol đã phát hiện và các Unicode identifier/content term có tín hiệu cao của từng file. Tokenizer giữ dạng Unicode gốc cùng dạng bỏ dấu để so khớp; một số cụm kỹ thuật tiếng Việt phổ biến được mở rộng sang alias gần với identifier trong code như login/session/expiry, và project có thể bổ sung alias riêng trong config. Khi refresh incremental, chỉ file thay đổi mới phải index lại. `content-hashes.json` lưu riêng content hash phục vụ verification để fingerprint lặp lại có thể dùng lại hash của file không đổi thay vì mở và hash lại toàn bộ source.

Để xác định cache còn hợp lệ, runtime dùng Git HEAD, hash của file dirty/untracked và hash cấu hình runtime. Đường dẫn Git được đọc bằng output phân cách NUL để giữ đúng Unicode, khoảng trắng và rename. Repository Git index file tracked và file untracked không bị ignore, trong giới hạn file và quy tắc loại trừ thư mục của kit. File generated bị ignore không vào graph trừ khi đã tracked; ngoài Git, scanner filesystem vẫn hoạt động và refresh đầy đủ.

`index.use_git_delta=false` tắt incremental refresh: cache hợp lệ vẫn được dùng khi không có thay đổi, nhưng repository đã thay đổi sẽ full rebuild. `impact` refresh qua cùng cache engine trước khi tính consumer và test bị ảnh hưởng. Thuật toán phát hiện cycle không dùng đệ quy nên dependency chain sâu không làm vượt giới hạn recursion của Python.

### Các cache mode

Mỗi lần refresh context/dependency sẽ rơi vào một trong ba trạng thái:

```text
CACHE_HIT
    repository state không đổi
    -> dùng lại last context/dependency

INCREMENTAL_REFRESH
    phát hiện Git delta
    -> chỉ update file thay đổi / language slice bị ảnh hưởng

FULL_REBUILD
    lần chạy đầu, cache thiếu/hỏng, Git delta không khả dụng,
    schema/scanner không tương thích, hoặc user force rebuild
```

Cache hit giúp tiết kiệm công việc. Nó **không** có nghĩa code đã pass test.

Trước khi dùng lại hoặc cập nhật incremental dependency graph, runtime kiểm tra cấu trúc node, edge, dependency map và cycle trong cache. JSON hỏng hoặc graph sai cấu trúc sẽ kích hoạt full rebuild thay vì bị coi là graph rỗng. Khi scanner được nâng cấp, cache của phiên bản cũ tự động bị vô hiệu hóa.

### Incremental refresh theo ngôn ngữ

Baseline không dependency ngoài hiện hoạt động như sau:

- Python — refresh source file đã thay đổi, dùng universe path Python hiện tại để resolve local import. Khi thêm, xóa hoặc đổi tên source path Python, runtime refresh toàn bộ Python slice để resolve lại import trong cả file không đổi. Scanner ghi nhận mọi local module được import, bao gồm nhiều import trong một câu lệnh và submodule của package.
- JavaScript/TypeScript — refresh file đã thay đổi cho relative import/export/require, alias `tsconfig`/`jsconfig`, alias `@/` có thể xác định tĩnh và import/export của local workspace package. Khi thêm, xóa/đổi tên source path hoặc thay đổi `package.json`/`tsconfig*`/`jsconfig.json`, runtime refresh toàn bộ JS/TS slice để resolve lại importer không đổi.
- Vue/Svelte single-file component — vẫn được track như source/context node dù dependency parsing trong embedded script chỉ là best-effort; framework context nhận diện component/route và native tooling vẫn là nguồn chính.
- PHP — refresh PHP slice khi file PHP hoặc Composer manifest thay đổi.
- Java/Kotlin — refresh JVM slice khi source JVM hoặc Maven/Gradle manifest thay đổi.
- Go — refresh Go slice khi file Go hoặc `go.mod` thay đổi.
- Rust — refresh Rust slice khi file Rust hoặc `Cargo.toml` thay đổi.

Thiết kế này cố ý đơn giản hơn việc thêm database/index service cho một personal-project kit.

### Relevant context có giới hạn

Fact của task hiện tại được materialize tại:

```text
.vibe/runtime/
├── current-task.json
├── project-map.json
├── framework-map.json
├── active-adapter.json
├── architecture-policy.json
├── dependency-map.json
├── relevant-context.json
├── impact.json
├── dependency-diff.json
└── verification.json
```

`relevant-context.json` cố ý nhỏ.

Giới hạn mặc định cho lần retrieval đầu:

- 20 source file,
- 10 test file,
- 8 module liên quan,
- dependency depth 2.

`relevant` xếp hạng target ban đầu từ filename/path cộng persistent Unicode symbol/content index, lưu evidence match, rồi mở rộng theo dependency neighborhood có giới hạn. Query normalization giữ Unicode, thêm dạng bỏ dấu và áp dụng query alias built-in/cấu hình thêm. Nếu top indexed score thấp hơn `context.retrieval.min_index_score`, runtime chạy bounded content fallback thay vì âm thầm chấp nhận một match yếu.

`relevant-context.json` ghi `retrieval_confidence`, `fallback` và `needs_scoped_search`. Fallback bị cắt giới hạn hoặc kết quả low-confidence được coi là evidence gap rõ ràng: agent phải dùng project-native search có phạm vi, xác định explicit target rồi chạy lại `relevant`/`impact`, không được suy ra rằng không còn file nào bị ảnh hưởng.

Với repository polyglot, persistent cache vẫn giữ stack ở cấp project. Task hiện tại sau đó chọn task-aware primary language từ extension của explicit target và evidence framework/language trong request. Task view này được materialize vào `active-adapter.json` và `architecture-policy.json` mà không buộc full re-index toàn project.

Cấu hình retrieval mặc định:

```json
{
  "context": {
    "retrieval": {
      "min_index_score": 6,
      "fallback_max_scan_files": 20000,
      "fallback_read_bytes": 131072,
      "query_aliases": {}
    }
  }
}
```

Full dependency graph có thể nằm trên disk nhưng không nên paste toàn bộ vào model context.

### Task history là cold storage

Audit record của từng task nằm tại:

```text
.vibe/tasks/<task-id>/
├── request.md
├── task.json
├── context.json
├── framework.json
├── active-adapter.json
├── architecture-policy.json
├── relevant-context.json
├── impact.json
├── plan.md
├── working-tree-before.md
├── acceptance.md
├── dependency-before.json
├── dependency-after.json
├── dependency-diff.json
└── verification.json
```

Agent viết `plan.md`, `working-tree-before.md` và `acceptance.md`; runtime ghi các JSON artifact. Working-tree record phân biệt chỉnh sửa sẵn có của user với thay đổi của task. Acceptance evidence ánh xạ từng tiêu chí trong plan tới kiểm tra và kết quả thực tế.

Policy mặc định:

```json
{
  "tasks": {
    "auto_load_history": false,
    "retention": {
      "policy": "bounded",
      "max_tasks": 100,
      "max_age_days": 90,
      "cleanup": "manual"
    }
  }
}
```

Session mới không được enumerate và load tất cả task cũ.

Task record được giữ cho tới khi có cleanup rõ ràng. `tasks.keep_history` vẫn không được dùng để tắt history: giá trị `true` cũ được chấp nhận, còn `false` báo lỗi cấu hình rõ ràng thay vì âm thầm vô hiệu hóa evidence. Retention policy chỉ xác định candidate, không tự xóa. Preview bằng `python .vibe/tools/vibe.py task gc`; chỉ khi user chủ động muốn dọn history mới chạy `python .vibe/tools/vibe.py task gc --apply`. Current task không bao giờ là cleanup candidate. ID task mới có suffix ngẫu nhiên và thư mục được tạo độc quyền, tránh dùng chung bằng chứng khi hai request xuất hiện trong cùng giây. Khi tiếp tục công việc, tái sử dụng current task thay vì gọi lại `task start`.

Task lịch sử chỉ được đọc khi:

- user nhắc rõ task trước đó, hoặc
- evidence hiện tại xác định một task cũ cụ thể thực sự liên quan.

Source/tests/config hiện tại luôn có độ ưu tiên cao hơn artifact lịch sử.

### Vì sao cách này tiết kiệm token

Repository scan và graph maintenance chạy trong deterministic Python code.

Model chỉ thấy relevant neighborhood có giới hạn:

```text
large repository
      ↓
persistent local cache
      ↓
Git delta
      ↓
relevant subgraph
      ↓
bounded source/tests
      ↓
LLM
```

Repo 5.000 file không đồng nghĩa model phải đọc 5.000 file.

## Config mặc định cho project cá nhân

Config v0.8 mặc định được giữ đơn giản:

```json
{
  "version": 3,
  "architecture": {
    "profile": "auto",
    "default_profile": "standard",
    "module_style": "feature-first",
    "default_pattern": "modular-layered",
    "strict_pattern": "hexagonal",
    "framework_conventions": "prefer",
    "allow_auto_strict": true,
    "strict_thresholds": {
      "source_files": 300,
      "feature_roots": 20
    }
  },
  "context": {
    "strategy": "persistent-incremental",
    "max_dependency_depth": 2,
    "max_files": 20000,
    "max_source_files": 20,
    "max_test_files": 10,
    "max_related_modules": 8,
    "retrieval": {
      "min_index_score": 6,
      "fallback_max_scan_files": 20000,
      "fallback_read_bytes": 131072,
      "query_aliases": {}
    }
  },
  "index": {
    "backend": "json",
    "use_git_delta": true,
    "full_rebuild_on_schema_change": true
  },
  "dependency": {
    "fail_on_new_cycles": true
  },
  "verification": {
    "require_commands": true,
    "commands": []
  },
  "tasks": {
    "auto_load_history": false,
    "retention": {
      "policy": "bounded",
      "max_tasks": 100,
      "max_age_days": 90,
      "cleanup": "manual"
    }
  }
}
```

Mặc định không dùng SQLite hoặc symbol database bắt buộc.

### Kiến trúc frontend mặc định

Frontend vẫn theo feature-first nhưng **không** bị ép theo ceremony backend kiểu controller/service/repository.

Cấu trúc điển hình:

```text
route/page shell
      ↓
feature UI
      ↓
hooks / composables / stores
      ↓
API / data adapters
```

Rule hữu ích:

- page/route shell nên mỏng,
- business workflow không nên nằm trong presentational component,
- tránh import internal của feature khác,
- shared module không phụ thuộc feature internals,
- tôn trọng server/client boundary trong Next.js, Nuxt và SvelteKit,
- dùng component/integration test cho UI behavior và chỉ dùng E2E cho critical flow.

### Kiến trúc WordPress mặc định

WordPress được coi là CMS/framework adapter, không chỉ là generic PHP.

Profile standard ưu tiên:

```text
WordPress hooks / REST / templates
            ↓
feature-oriented plugin/theme modules
            ↓
services / business behavior
            ↓
WordPress APIs / data adapters
```

Adapter coi hook, filter, shortcode, REST route, block contract, option/meta và boundary plugin/theme là integration contract. Nó ưu tiên WordPress API và custom plugin/theme code thay vì sửa WordPress core.

## Workflow cốt lõi

### Full workflow

```text
PLAN -> BUILD -> VERIFY
```

Ví dụ:

```text
Use vibe to add percentage-based trailing stops while preserving old fixed-point configs.
```

Yêu cầu triển khai cho phép thực hiện plan/build/verify trong phạm vi đã yêu cầu mà không cần xin duyệt plan thêm lần nữa. Yêu cầu chỉ lập kế hoạch dừng sau plan. Vẫn tuân thủ bước phê duyệt do user yêu cầu rõ ràng và làm rõ quyết định còn thiếu nếu nó ảnh hưởng đáng kể tới kết quả.

### Plan

Skill plan:

1. Đọc `AGENTS.md` và `.vibe/config.json`.
2. Đọc current task và tái sử dụng khi tiếp tục cùng mục tiêu; chỉ tạo record cho mục tiêu mới.
3. Ghi nhận thay đổi staged, unstaged và untracked có sẵn vào `working-tree-before.md` trước implementation; giữ nguyên record khi tiếp tục task.
4. Chạy `context --summary` và `deps --summary` để refresh facts, giữ graph đầy đủ trên đĩa.
5. Chạy `relevant` và bắt đầu từ bounded context cho source/test/module. Nếu kết quả rỗng hoặc không liên quan, tìm filename/symbol có giới hạn rồi xác định target cụ thể.
6. Chỉ tạo `snapshot before` trước implementation và khi task chưa có baseline; replanning không thay thế baseline ban đầu.
7. Chạy impact analysis và chỉ mở rộng context khi evidence yêu cầu.
8. Tạo plan với acceptance criteria quan sát được (`AC1`, `AC2`, v.v.), ánh xạ tới test, command hoặc kiểm tra thủ công; ghi rõ khoảng trống bằng chứng.

### Build

Build:

- chỉ đọc current task,
- bắt đầu từ `relevant-context.json`,
- tuân architecture policy,
- tạo diff nhỏ nhất đúng yêu cầu,
- thực hiện acceptance criteria với kiểm tra phù hợp,
- giữ nguyên chỉnh sửa sẵn có, kể cả hunk không liên quan trong target file,
- chỉ mở rộng context khi có evidence.

Kiến trúc standard vẫn được dùng ports/adapters hoặc abstraction khác khi có nhu cầu cụ thể về boundary, variation, reuse hoặc testing. Không bắt buộc áp dụng toàn bộ cấu trúc Clean/Hexagonal.

### Verify

Verify:

- refresh context/dependency bằng cùng cache/delta engine,
- capture dependency state sau thay đổi khi có baseline hợp lệ từ trước implementation,
- so sánh dependency snapshot hoặc báo rõ thiếu khả năng so sánh,
- phát hiện cycle mới,
- chạy lint/type/test/build command đã cấu hình,
- review diff unstaged, staged và file untracked liên quan dựa trên working-tree record ban đầu,
- lưu kết quả runtime trong `verification.json` và evidence cho từng tiêu chí trong `acceptance.md` do agent viết.

`CACHE_HIT` không được dùng để bỏ qua verification command.

Runtime status và kết quả acceptance được báo riêng. Mỗi tiêu chí có trạng thái `met`, `unmet` hoặc `unverified`, kèm evidence thực tế và giới hạn. Chỉ pass các command đã cấu hình chưa đủ để hoàn tất task còn thiếu bằng chứng bắt buộc. Sửa code/test/configuration sau đó phải chạy lại kiểm tra bị ảnh hưởng và final runtime verification; sửa riêng tài liệu cần kiểm tra tài liệu phù hợp.

Xử lý lỗi theo nguyên nhân: lỗi code quay về build; sai scope/criteria quay về plan; thiếu verification configuration cần xác định check có sẵn của project; lỗi môi trường cần chẩn đoán tool/configuration bị thiếu. Nếu thiếu runtime, dùng check của project và ghi rõ giới hạn runtime verification. Baseline thiếu/hỏng sau khi đã sửa code phải được báo rõ, không được dựng giả. Chỉ retry khi chẩn đoán hoặc thay đổi cụ thể mở ra hướng xử lý; nếu không, báo blocker và hành động cần thiết.

## Các change mode

### Feature

Tập trung vào:

- desired behavior,
- vị trí kiến trúc,
- dependency impact,
- acceptance criteria,
- focused tests.

### Change

Tập trung vào:

- current behavior,
- desired behavior,
- compatibility,
- consumer bị ảnh hưởng,
- migration impact cho schema/config/API.

### Bug fix

Chuỗi bắt buộc:

```text
REPRODUCE
-> ROOT CAUSE
-> FAILING REGRESSION TEST
-> MINIMAL FIX
-> PASSING REGRESSION TEST
-> AFFECTED TESTS
-> VERIFY
```

Không được kết luận bug đã fix chỉ vì symptom biến mất khi test thủ công.

### Refactor

Tập trung vào:

- capture baseline behavior,
- dependency snapshot trước,
- giữ nguyên public behavior/contract,
- dependency snapshot sau,
- chứng minh behavior không đổi.

### Hotfix

Rule:

- scope tối thiểu,
- không cleanup ngoài lề,
- không upgrade dependency nếu không cần,
- reproduce khi thực tế làm được,
- regression test,
- critical affected verification.

## Chính sách test

Kit không bắt buộc mỗi function phải có một direct unit test.

Rule ưu tiên là:

```text
100% non-trivial business behavior
nên có meaningful test coverage
```

Nên test trực tiếp khi thực tế:

- public business behavior,
- calculation,
- validation rule,
- branch quan trọng,
- failure/error behavior,
- bug regression.

Có thể cover gián tiếp:

- private helper,
- mapping đơn giản,
- framework glue,
- getter/setter trivial,
- generated code.

Chiến lược thường dùng:

```text
business logic
-> focused unit tests

repository/database boundary
-> integration tests khi hữu ích

API endpoints
-> request/response integration tests

critical user flows
-> E2E khi thực sự cần

bug
-> regression test bắt buộc khi thực tế
```

Test nên assert observable behavior thay vì internal call count hoặc implementation detail, trừ khi chính implementation contract là phần cần bảo vệ.

## Runtime CLI

```bash
python .vibe/tools/vibe.py detect
python .vibe/tools/vibe.py task start --mode bug_fix --request "stop-loss gap fill is wrong"
python .vibe/tools/vibe.py context --summary
python .vibe/tools/vibe.py adapter
python .vibe/tools/vibe.py framework
python .vibe/tools/vibe.py architecture
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py deps --summary
python .vibe/tools/vibe.py relevant
python .vibe/tools/vibe.py relevant src/orders/service.py
python .vibe/tools/vibe.py relevant --query "fix order cancellation"
python .vibe/tools/vibe.py impact
python .vibe/tools/vibe.py task gc
python .vibe/tools/vibe.py task gc --apply
python .vibe/tools/vibe.py snapshot before
python .vibe/tools/vibe.py snapshot after
python .vibe/tools/vibe.py verify --summary
python .vibe/tools/vibe.py status
python .vibe/tools/vibe.py rebuild
```

Command quan trọng:

- `state` — cho biết persistent context/dependency sẽ được reuse hay refresh.
- `relevant` — tạo bounded context cho task và báo retrieval confidence/fallback evidence.
- `task gc` — preview cleanup task history theo retention policy; chỉ thêm `--apply` khi thực sự muốn xóa.
- `rebuild` — ép full rebuild context/dependency để debug hoặc sau thay đổi cấu trúc lớn.

`context`, `deps` và `verify` nhận hai flag loại trừ nhau `--summary` và `--quiet` sau tên command. Mặc định vẫn xuất JSON đầy đủ. `--summary` in số lượng/trạng thái và đường dẫn artifact, không in chi tiết graph, danh sách file hoặc command log; `--quiet` tắt stdout. Cả hai vẫn ghi artifact đầy đủ và giữ nguyên exit code cùng lỗi trên stderr. Exit code của verification là `0` cho `PASS_VERIFIED`, `1` cho verification thất bại/lỗi runtime và `3` khi thiếu command configuration. Khi có lỗi, đọc command result liên quan trong `verification.json`, không coi command im lặng là thành công.

Verification summary có trường `dependency_comparison_available`; khi là false, số cycle mới trong summary không chứng minh rằng thay đổi không tạo cycle mới.

## Phân tích dependency

Baseline built-in không yêu cầu dependency ngoài:

- Python — AST local import graph.
- JavaScript/TypeScript — relative import cộng alias path `tsconfig`/`jsconfig`, alias source `@/` có thể xác định tĩnh và local npm/yarn/pnpm workspace package import/export.
- PHP — namespace/use cộng literal require/include.
- Java/Kotlin — package/import relationship.
- Go — local module import relationship.
- Rust — module declaration và `crate::` use relationship.
- Khác — project/file map.

Framework context được materialize vào `.vibe/runtime/framework-map.json`.

Toàn bộ language adapter đã detect, repository primary language, task-aware primary language và framework adapter được materialize vào `.vibe/runtime/active-adapter.json`. Trong project polyglot, explicit target file có tín hiệu mạnh nhất cho task primary, sau đó là framework/language trong request; repository priority chỉ là fallback.

Bản reusable nằm dưới `.vibe/state/`.

Built-in dependency graph khai báo `authority.level = advisory` và `model = static-best-effort`. Graph dùng để thu hẹp retrieval/impact, không phải bằng chứng rằng không còn runtime dependency nào khác. Dynamic import, DI container, generated code/route, framework registry, runtime wiring của Rails/WordPress, macro hoặc alias chỉ tồn tại ở bundler vẫn cần native analyzer, test hoặc kiểm tra trực tiếp khi có liên quan.

### Tool native khuyến nghị

Python:

- Grimp
- Import Linter
- Ruff
- Pyright hoặc mypy
- pytest

TypeScript/JavaScript:

- dependency-cruiser
- Nx cho monorepo
- TypeScript compiler
- ESLint
- Vitest/Jest/Playwright

PHP/Laravel:

- Deptrac
- PHPStan/Larastan
- Pest/PHPUnit
- Laravel Pint/PHP-CS-Fixer

Java/Spring:

- Maven/Gradle dependency tooling
- ArchUnit
- jdeps
- Checkstyle/SpotBugs

Go:

- `go list -deps`
- `go mod graph`
- `go vet`
- staticcheck/golangci-lint
- `go test ./...`

Rust:

- `cargo metadata`
- `cargo tree`
- `cargo clippy`
- `cargo test`

Graph built-in là baseline zero-setup. Native analyzer vẫn là nguồn chính khi project đã cấu hình.

Với frontend, native tooling hữu ích gồm ESLint, TypeScript/Vue/Svelte type-checker, Vitest/Jest, Testing Library, Playwright/Cypress và framework build command. Với WordPress, nên dùng Composer script, PHPUnit/Pest, PHPStan, PHPCS/WordPress Coding Standards, WP-CLI check và frontend build/test command nếu project đã cấu hình.

## Dependency snapshot

Trước implementation:

```bash
python .vibe/tools/vibe.py deps --summary
python .vibe/tools/vibe.py snapshot before
```

Sau implementation:

```bash
python .vibe/tools/vibe.py deps --summary
python .vibe/tools/vibe.py snapshot after
```

Snapshot tự refresh dependency hiện tại. `snapshot before` giữ nguyên baseline hợp lệ đã có và từ chối ghi đè baseline hỏng. `snapshot after` và dependency comparison yêu cầu baseline gốc hợp lệ, không thay bằng graph rỗng khi thiếu bằng chứng. Không tạo `snapshot before` sau khi implementation đã bắt đầu. Tiếp tục công việc thì tái sử dụng current task; retry hoặc sửa plan không phải task mới.

Diff gồm:

- edge thêm,
- edge bỏ,
- cycle mới,
- cycle được bỏ,
- số node before/after.

## Verification semantics

Các trạng thái:

- `PASS_VERIFIED`
- `FAIL_VERIFICATION`
- `NEEDS_VERIFICATION_CONFIG`

Chỉ được tạo `PASS_VERIFIED` khi:

1. deterministic context/dependency work hoàn tất,
2. phép so sánh before/after khi khả dụng không phát hiện forbidden new cycle,
3. ít nhất một verification command đã được cấu hình,
4. command thực sự được chạy,
5. tất cả required command đều thành công.

Cache hit không bao giờ đủ để làm bằng chứng cho `PASS_VERIFIED`.

Verification chạy các command đã cấu hình trước khi chụp dependency graph cuối cùng và snapshot after. Fingerprint đầu vào trước/sau mỗi command được ghi lại. Nếu command thay đổi file được index hoặc cấu hình runtime, kết quả là `FAIL_VERIFICATION` với `rerun_required: true` và `rerun_commands` liệt kê toàn bộ kiểm tra đã cấu hình. Review thay đổi cuối cùng rồi chạy lại các kiểm tra đó; muốn pass thì đầu vào phải ổn định. Đặt output tạm của command trong thư mục bị ignore để không coi đó là đầu vào verification.

`verification.json` có `task_id` và `source_fingerprint` (SHA-256 của đường dẫn/nội dung file được index và cấu hình runtime, trong giới hạn file đã cấu hình). Fingerprint đầu tiên tạo `content-hashes.json`; các fingerprint sau dùng repository delta để chỉ hash lại file mới/thay đổi và tái sử dụng hash của file không đổi. `status.verification_current` đối chiếu fingerprint và task identity; trường này cho biết report còn hiện hành, không đồng nghĩa đã pass. Verify summary cũng có các định danh này, `rerun_required` và authority level của dependency graph để agent không nhầm static evidence với runtime proof. Executable được resolve qua PATH/PATHEXT trước khi chạy, bao gồm package-manager shim `.CMD` trên Windows, không bật `shell=True`. CI bao phủ Linux, Windows và macOS trên Python 3.9, 3.11 và 3.13.

Danh sách command rỗng trả về `NEEDS_VERIFICATION_CONFIG` (CLI exit code `3`), kể cả khi `verification.require_commands` là `false`. Setting này không cho phép bỏ qua yêu cầu thực sự chạy kiểm tra trước khi báo `PASS_VERIFIED`.

Khi không có baseline gốc, standalone verification vẫn có thể báo các check đã cấu hình pass với `dependency_diff: null`; đó không phải bằng chứng về cycle mới phát sinh. Skill báo riêng giới hạn này và các acceptance criteria unmet/unverified thay vì kết luận toàn bộ task hoàn tất. Baseline đã tồn tại nhưng hỏng sẽ gây lỗi và được giữ nguyên để chẩn đoán.

## Cấu trúc repository

Source repository:

```text
my-vibe-kit/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── README_vi.md
├── install.py
├── vibe.config.example.json
├── skills/
│   ├── vibe/SKILL.md
│   ├── plan/SKILL.md
│   ├── build/SKILL.md
│   └── verify/SKILL.md
├── runtime/
│   ├── vibe.py
│   ├── vibe_core.py
│   ├── vibe_retrieval.py
│   ├── vibe_tasks.py
│   ├── vibe_stacks.py
│   ├── vibe_architecture.py
│   ├── vibe_contracts.py
│   ├── vibe_security.py
│   ├── vibe_workflow.py
│   └── vibe_state.py
├── schemas/
│   └── contracts-v1.json
├── benchmarks/
│   └── benchmark_runtime.py
├── adapters/
│   ├── languages/
│   └── frameworks/
├── integrations/
├── templates/
└── tests/
```

Project sau khi cài:

```text
your-project/
├── AGENTS.md
├── CLAUDE.md
├── .agents/
│   ├── skills/
│   ├── rules/
│   └── workflows/
├── .claude/
│   └── skills/
└── .vibe/
    ├── config.json
    ├── adapters/
    ├── tools/
    ├── state/       # persistent local cache; ignored
    ├── runtime/     # current-task materialization; ignored
    └── tasks/       # cold task history; not auto-loaded
```

## Yêu cầu môi trường

- Python 3.9+
- Git
- Ít nhất một coding agent được hỗ trợ

Runtime của kit chỉ dùng Python standard library.

Project đích có thể dùng ngôn ngữ/toolchain phù hợp với adapter hỗ trợ.

## Tương thích agent

| Surface | Project skills | Personal/global skills | Ghi chú |
| --- | --- | --- | --- |
| Codex desktop / CLI / IDE | `.agents/skills/` | `~/.agents/skills/` | Nên cài theo project để có deterministic runtime |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | Native filesystem skill discovery |
| Claude app / claude.ai | upload ZIP | upload ZIP | Dùng `python install.py --bundle-claude` |
| Antigravity IDE | `.agents/skills/` | `~/.gemini/config/skills/` | Project install thêm rules/workflows |
| Antigravity CLI | `.agents/skills/` | `~/.gemini/antigravity-cli/skills/` | Nên dùng project scope |

Để có deterministic context/dependency/verification đầy đủ, hãy cài kit trực tiếp vào từng target repository.

## Cài riêng theo agent

### Codex

Project:

```bash
python install.py --target /duong-dan/toi/project --agents codex
```

Global:

```bash
python install.py --scope global --agents codex
```

### Claude Code

Project:

```bash
python install.py --target /duong-dan/toi/project --agents claude
```

Global:

```bash
python install.py --scope global --agents claude
```

Tạo ZIP để upload lên các surface Claude hỗ trợ custom skill:

```bash
python install.py --bundle-claude
```

### Google Antigravity

Project:

```bash
python install.py --target /duong-dan/toi/project --agents antigravity
```

Global:

```bash
python install.py --scope global --agents antigravity
```

Project install cũng thêm Antigravity rules và slash workflows.

## Setup lần đầu

Sau khi cài, kiểm tra:

```text
.vibe/config.json
```

Installer detect stack, seed architecture/context defaults và tự tìm verification commands khi đủ chắc chắn.

Ví dụ:

- Node/TypeScript — package script `lint`, `typecheck`, `test`, `build`.
- Python — Ruff, Pyright/mypy, pytest khi đã khai báo.
- Django — `python manage.py check` và Django tests khi phù hợp.
- Laravel/PHP — Composer scripts, PHPStan/Larastan, Pest/PHPUnit, `php artisan test`.
- Ruby/Rails — RuboCop và RSpec khi đã khai báo; nếu không có RSpec thì Rails dùng `bundle exec rails test`.
- Java/Spring — Maven/Gradle tests.
- Go — `go test ./...`.
- Rust — `cargo check`, `cargo test`.

Nếu không tìm được verification command đáng tin cậy, hãy cấu hình thủ công.

Ví dụ:

```json
{
  "verification": {
    "require_commands": true,
    "commands": [
      ["python", "-m", "ruff", "check", "."],
      ["python", "-m", "pytest", "-q"]
    ]
  }
}
```

## Cập nhật project đã cài kit

Update source kit:

```bash
cd /duong-dan/toi/my-vibe-kit
git pull
```

Preview:

```bash
python install.py --target /duong-dan/toi/project --agents all --dry-run
```

Apply managed update:

```bash
python install.py --target /duong-dan/toi/project --agents all --force
```

`--force` refresh managed runtime/skill/integration file nhưng cố ý giữ nguyên file do project sở hữu:

- `AGENTS.md`
- `CLAUDE.md`
- `.vibe/config.json`

Khi nâng cấp installation cũ, nên so config project với `vibe.config.example.json`. Runtime có default an toàn cho key v3 bị thiếu, nhưng merge rõ các setting context/index/task mới vẫn là lựa chọn tốt hơn.

## Hành vi cài đặt an toàn

Installer:

- tạo managed file còn thiếu,
- không đụng file project không liên quan,
- giữ nguyên instruction/config project đã có,
- báo managed-file conflict,
- hỗ trợ `--dry-run`, kể cả Claude bundle mà không tạo thư mục hoặc ghi đè ZIP,
- giữ nguyên `install-manifest.json` bị conflict trừ khi có `--force`,
- loại `__pycache__`, `.pyc` và `.pyo` khỏi file cài đặt và bundle,
- chỉ refresh file do kit quản lý khi dùng `--force`.

Nên review diff của target repository trước khi commit.

## Cách dùng hằng ngày

Phần lớn task:

```text
Use vibe to implement <request>.
```

Task rủi ro:

```text
Use plan to phân tích việc đổi SQLite sang PostgreSQL. Chưa sửa code.
```

Sau đó:

```text
Use build cho current task, sau đó verify.
```

Manual inspection hữu ích:

```bash
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py relevant
python .vibe/tools/vibe.py status
```

## Troubleshooting

### Agent không phát hiện skill

Codex / Antigravity:

```text
.agents/skills/<skill-name>/SKILL.md
```

Claude Code:

```text
.claude/skills/<skill-name>/SKILL.md
```

Restart/reopen agent nếu skill được thêm khi agent đang chạy.

### Verification yêu cầu cấu hình

Chỉnh:

```text
.vibe/config.json
```

và thêm command đại diện cho quality gate thật của project.

### Dependency map bỏ sót framework magic

Static graph không thể thấy mọi dynamic import, plugin registry, reflection path, runtime DI binding, generated source, macro hoặc external service.

Hãy document runtime relationship quan trọng trong project instruction/architecture docs và cấu hình native analyzer/test phù hợp.

### Repository lớn tạo quá nhiều context

Kiểm tra:

```bash
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py relevant
```

Giới hạn mặc định cho lần đầu là 20 source file, 10 test, 8 module liên quan, dependency depth 2.

Chỉ tăng giới hạn khi task thực tế cần neighborhood rộng hơn.

Không paste `last-dependency.json` hoặc toàn bộ dependency graph vào model context.

### Cache có vẻ stale hoặc repository vừa thay đổi cấu trúc lớn

Kiểm tra:

```bash
python .vibe/tools/vibe.py state
```

Sau đó rebuild:

```bash
python .vibe/tools/vibe.py rebuild
```

## Performance benchmark

Repo có benchmark synthetic chỉ dùng Python standard library tại `benchmarks/benchmark_runtime.py`. Mặc định benchmark tạo Git repository với **1.000 / 5.000 / 20.000 Python source file** và đo:

- full context rebuild,
- dependency graph construction,
- context/dependency cache hit,
- multilingual task retrieval,
- single-file incremental context refresh,
- single-file incremental dependency refresh.

Chạy full benchmark:

```bash
python benchmarks/benchmark_runtime.py --sizes 1000 5000 20000
```

Xuất JSON:

```bash
python benchmarks/benchmark_runtime.py --sizes 1000 5000 20000 --json
```

CI chạy một benchmark smoke nhỏ. Workflow GitHub Actions `performance-benchmark` chạy thủ công hoặc khi publish release cho full 1k/5k/20k. Workflow restore baseline gần nhất trên cùng runner, ghi delta phần trăm dạng diagnostic vào `benchmark-comparison.json`, cache kết quả hiện tại làm baseline kế tiếp và upload artifact gắn SHA trong 90 ngày. So sánh này không phải hard pass/fail threshold vì thời gian tuyệt đối phụ thuộc tải runner và môi trường.

### Vì sao không dùng SQLite?

Kit chủ yếu dành cho project cá nhân.

JSON + Git delta:

- dễ inspect,
- dễ xóa/rebuild,
- chỉ dùng standard library,
- dễ debug,
- đủ cho repository cá nhân thông thường.

Chỉ nên thêm SQLite hoặc symbol-level indexing khi repository thực tế chứng minh JSON load hoặc file-level retrieval đã trở thành bottleneck.

## Triết lý

```text
LLM       -> reasoning và implementation
Scripts   -> deterministic repository facts
State     -> reusable local cache, không phải truth tự thân
Tests     -> behavioral truth
Git       -> history, delta detection, rollback
Skills    -> reusable workflow
AGENTS.md -> durable project rules
```

Mục tiêu không phải autonomy bằng mọi giá.

Mục tiêu là personal vibe coding **đơn giản, dễ kiểm tra, lặp lại được, tiết kiệm token và khó fake kết quả**.

## License

MIT
