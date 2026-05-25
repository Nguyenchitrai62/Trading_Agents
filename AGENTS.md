# TradingAgents Workspace Context

## Product Goal

Xây dựng một hệ thống agent phân tích thị trường có thể dùng thực tế với các thành phần sau:

- FE tách riêng, deploy trên Vercel.
- BE tách riêng, deploy trên Render.
- DB là tùy chọn, chỉ thêm khi thực sự cần lưu trữ bền vững. Ưu tiên MongoDB hoặc Turso.
- Telegram bot là một lớp giao tiếp bổ sung, gọi lại cùng backend/service layer, không nhân bản logic phân tích.

Mục tiêu sản phẩm không phải là giữ nguyên CLI cũ. Mục tiêu là giữ lại và phát triển phần backend agent orchestration, sau đó đẩy kết quả phân tích theo thời gian thực lên FE và các kênh tích hợp khác.

## Architecture Target

- FE dùng HTML, CSS, JavaScript thuần. Không tự ý thêm React, Vue, Next.js hoặc framework FE khác nếu chưa có yêu cầu rõ ràng.
- BE dùng FastAPI.
- Luồng phân tích chính phải là streaming theo thời gian thực bằng Server-Sent Events (SSE).
- FE phải có khả năng chọn cấu hình rồi bấm chạy phân tích; trong khi BE đang xử lý, FE phải cập nhật liên tục các vùng UI tương ứng với từng agent/team/report.
- Backend phải tái sử dụng core trong thư mục `tradingagents/`, không xây một pipeline agent song song mới nếu không thật sự cần.

## Current Implementation

- Backend entrypoint hiện tại là `app.py`.
- Frontend hiện tại là `index.html`, `FE/app.js`, `FE/styles.css`.
- FE hiện đã là dashboard nhiều window theo tinh thần TradingAgents CLI:
  - Execution Board
  - Report Windows
  - Research Chamber
  - Trader Desk
  - Risk Room
  - Final Decision
  - Event Log
- Popup config hiện hỗ trợ:
  - symbol
  - analysis date
  - lookback window
  - output language
  - analyst selection
  - research depth
  - model
  - checkpoint toggle
- `/api/analyze` là endpoint chính cho luồng phân tích streaming.
- `/api/analyze` stream các event như `analysis_meta`, `status_snapshot`, `section_update`, `debate_update`, `warning`, `complete`, `error`.
- FE đang map các event này vào các panel UI tương ứng.
- `/api/analyze` là API phân tích chính; endpoint chat thử nghiệm cũ đã được loại bỏ để giảm bề mặt API.

## Environment And Configuration

- Dùng `.env` cho runtime configuration.
- Base URL FE dùng để gọi backend khi chạy tách origin và các default analysis của FE được đặt trong `FE/config.js`.
- `MINIMAX_API_KEY` hoặc `MINIMAX_CN_API_KEY` phải nằm trong `.env` để backend gọi LLM.
- `MINIMAX_BASE_URL` dùng để trỏ tới anthropic-compatible MiniMax endpoint.
- `CORS_ALLOW_ORIGINS` phải được cấu hình theo domain FE thật khi deploy.

## Dependency Policy

- Chỉ dùng `requirements.txt` cho cài đặt dependency.
- Không tự ý khôi phục `pyproject.toml` hoặc chuyển repo về flow package build cũ nếu người dùng chưa yêu cầu.
- `requirements.txt` đang được giữ khá rộng để tránh thiếu thư viện khi mở rộng backend trong các bước tiếp theo.

## Deployment Intent

- FE: static hosting trên Vercel.
- BE: FastAPI trên Render.
- DB: chỉ thêm khi cần persistence thực sự, ví dụ:
  - lịch sử phân tích
  - cấu hình người dùng
  - logs dài hạn
  - báo cáo đã lưu
- Telegram bot: triển khai như client/adaptor gọi vào backend hiện có, không chèn logic agent trực tiếp vào bot.

## Working Priorities For Future Changes

1. Ưu tiên ổn định luồng FE -> BE -> SSE -> UI trước.
2. Mọi thay đổi UI phải giữ được khả năng hiển thị tiến trình agent theo thời gian thực.
3. Khi thêm DB, phải tách thành lớp persistence/service rõ ràng để không phá vỡ SSE flow hiện tại.
4. Khi thêm Telegram bot, phải tái sử dụng request models, config models và orchestration hiện có.
5. Khi mở rộng backend, ưu tiên mở rộng `app.py` và `tradingagents/` thay vì thêm các entrypoint rời rạc không liên kết.

## Non-Goals

- Không khôi phục lại toàn bộ repo cũ chỉ để giữ tài liệu, CLI hoặc artifact không phục vụ mục tiêu FE/BE hiện tại.
- Không biến FE hiện tại thành framework app lớn nếu chưa có yêu cầu cụ thể.
- Không thêm DB chỉ vì “có thể cần”; chỉ thêm khi xuất hiện nhu cầu persistence rõ ràng.

## Key Files

- `app.py`: FastAPI app, config bootstrap, SSE endpoints, MiniMax integration.
- `index.html`: shell của dashboard FE và bootstrap backend base URL.
- `FE/app.js`: logic FE, config modal, gọi API, parse SSE, render panels.
- `FE/styles.css`: giao diện dashboard.
- `tradingagents/graph/trading_graph.py`: core orchestration của TradingAgentsGraph.
- `tradingagents/graph/analyst_execution.py`: analyst node mapping và report mapping.
- `tradingagents/default_config.py`: default runtime config của graph.
- `.env.example`: tài liệu hóa các biến môi trường cần dùng.
- `requirements.txt`: nguồn cài dependency duy nhất.

## Definition Of Done For Core Product Work

Một thay đổi được xem là đi đúng hướng mục tiêu lớn khi thỏa các điều sau:

- FE có thể cấu hình phiên phân tích và gửi request xuống backend.
- Backend stream tiến trình phân tích liên tục thay vì chỉ trả kết quả cuối.
- FE cập nhật đúng panel theo từng bước agent/team/report.
- Cấu hình runtime giữ API key trong `.env`; riêng base URL FE và default analysis được quản lý trong `FE/config.js`.
- Thay đổi vẫn phù hợp với mô hình deploy FE trên Vercel và BE trên Render.

## Guidance For Coding Agents

- Luôn xem repo này như một sản phẩm multi-agent market analysis platform, không phải chỉ là demo chat với LLM.
- Nếu phải chọn giữa việc thêm tính năng ngắn hạn và giữ đúng kiến trúc FE/BE streaming dài hạn, ưu tiên kiến trúc dài hạn.
- Nếu cần thêm tích hợp mới, cố gắng nối nó vào backend/service layer hiện tại để mọi client (FE, Telegram, tác vụ sau này) dùng chung một luồng phân tích.