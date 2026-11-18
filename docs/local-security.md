# Local owner access / 本机所有者访问

Start the application with paperrule app and open the complete link printed in that terminal. The link includes a newly generated owner capability in its URL fragment. The browser exchanges it for a session cookie, removes the fragment from its address bar, and keeps the CSRF value in page memory. The capability is not saved in the private memory or public repository.

启动服务后，打开终端打印的完整链接即可进入网页。请保留运行服务的终端；重启服务后使用新链接。直接打开普通地址而没有有效会话时，网页会提示从终端进入。审批仍需在审批中心明确批准当前提案版本，登录本身不会批准任何规则。

The server accepts loopback clients with a localhost, 127.0.0.1 or ::1 Host. It rejects foreign API origins and cross-site fetch metadata, including requests carrying an otherwise valid owner capability. The CLI disables forwarded-header handling. The readiness endpoint /healthz exposes only a status; private APIs, diagnostics and the OpenAPI documentation require authentication.

Browser sessions use an HttpOnly, SameSite=Strict cookie. Mutating API requests using that cookie also need the matching X-CSRF-Token header. Sessions expire after eight hours and are kept only in process memory, with at most 32 sessions. A restart invalidates all previous sessions. The session API supports explicit logout with DELETE /api/session and its CSRF header.

Local programmatic HTTP clients may send Authorization: Bearer followed by the startup capability. Bearer requests still undergo loopback, Host and origin checks. They do not need the cookie-based CSRF header. A missing or invalid capability does not authorize a write. Existing direct PaperRule CLI operations use the private memory directly and retain their proposal-hash approval requirements.

These controls protect HTTP access and browser request boundaries. They do not isolate PaperRule from other programs running with the same operating-system account. Imported material remains untrusted, and authentication does not replace rule validation, explicit approval or privacy checks before publication.

Verification includes raw unauthenticated API tests, real proposal approval with session and CSRF checks, expiry and restart tests, and a browser workflow using no injected Authorization header. Other owner API tests authenticate explicitly through their test transport. Synthetic browser and API tests do not constitute an independent security audit.
