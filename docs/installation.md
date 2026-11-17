# Installation / 安装指南

PaperRule requires Python 3.12 or newer and Git. A distribution wheel includes the production web application; users installing that wheel do not need Node.js. Building from source additionally requires Node.js 22.12 or newer in the Node 22 series and npm.

请将公开程序与私有记忆分开保存。安装包包含网页；从源码开发时才需要构建网页。下面所有命令均在你自行选择的项目目录执行，不需要全局安装 Python 依赖。AI 未配置时可使用人工编辑和审批，语义审查不会因此显示为已完成。

## Install a distribution wheel

Use the wheel from a verified release or a successful distribution CI artifact. Availability of a release and passing operating-system checks must be verified separately; a local wheel build does not establish either.

Place paperrule-0.1.0-py3-none-any.whl in your chosen application directory. Git must already be available on PATH. The ingest extra installs PDF and DOCX parsers.

### Windows PowerShell

    python -m venv .venv
    ./.venv/Scripts/python.exe -m pip install "./paperrule-0.1.0-py3-none-any.whl[ingest]"
    $env:PAPERRULE_MEMORY = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path "../paperrule-private-memory"))
    ./.venv/Scripts/paperrule.exe init --workspace $env:PAPERRULE_MEMORY
    ./.venv/Scripts/paperrule.exe app

### Linux and macOS

    python3 -m venv .venv
    .venv/bin/python -m pip install "./paperrule-0.1.0-py3-none-any.whl[ingest]"
    export PAPERRULE_MEMORY="$(pwd)/../paperrule-private-memory"
    .venv/bin/paperrule init --workspace "$PAPERRULE_MEMORY"
    .venv/bin/paperrule app

Open the localhost address printed by the server. The application binds to 127.0.0.1. Keep the terminal open while using it; Ctrl+C stops the service. Set PAPERRULE_MEMORY again in a new terminal before starting the application. Keep using the same private-memory directory to preserve your records.

## Build from source

Run these commands at the root of the checkout:

    npm --prefix frontend ci --ignore-scripts
    npm --prefix frontend run build
    python -m venv .venv

On Windows:

    ./.venv/Scripts/python.exe -m pip wheel . --no-deps --wheel-dir dist
    ./.venv/Scripts/python.exe -m pip install "./dist/paperrule-0.1.0-py3-none-any.whl[ingest]"

On Linux and macOS:

    .venv/bin/python -m pip wheel . --no-deps --wheel-dir dist
    .venv/bin/python -m pip install "./dist/paperrule-0.1.0-py3-none-any.whl[ingest]"

Then initialize the private memory and start the service using the platform-specific commands above. A non-editable distribution build deliberately fails when the production web bundle is absent. Build the frontend first rather than distributing a package that opens a missing-workbench page.

## Development installation

Create the virtual environment in the checkout and install the development extras:

Windows:

    ./.venv/Scripts/python.exe -m pip install -e ".[dev,ingest]"

Linux and macOS:

    .venv/bin/python -m pip install -e ".[dev,ingest]"

Build the frontend before opening the normal application. Editable installs permit backend development without a built bundle; the root page then explains that the web application is unavailable. The editable install is not evidence that a distributable wheel contains the webpage.

## First use with synthetic feedback

1. Set PAPERRULE_MEMORY and initialize the separate private-memory directory.
2. Start the app and open its printed localhost URL.
3. In 来源与意见, paste synthetic feedback such as “Explain the synthetic assumption before the claim.”
4. Create a rule proposal, discuss or edit its wording and scope, then inspect the complete before/after contents in 审批中心.
5. Explicitly approve the exact current proposal version. Saving feedback or chatting does not approve a rule.
6. Check the rule in 规则知识库 and inspect its history. Add synthetic regression cases in 回归测试.

AI configuration and private-remote synchronization are separate setup tasks. Manual mode preserves feedback and proposals. Unavailable semantic checks remain unreviewed; a working installation does not prove model accuracy. A public application repository must never be used as the remote for private papers or feedback.

## Verify the wheel

After building the wheel, install its dependencies and httpx in the chosen virtual environment. Create a temporary directory inside the checkout and run:

Windows:

    ./.venv/Scripts/python.exe -m pip install "./dist/paperrule-0.1.0-py3-none-any.whl" httpx
    ./.venv/Scripts/python.exe -c "from pathlib import Path; Path('.test-tmp').mkdir(exist_ok=True)"
    ./.venv/Scripts/python.exe scripts/wheel_smoke.py dist/paperrule-0.1.0-py3-none-any.whl --temporary-root .test-tmp

Linux and macOS:

    .venv/bin/python -m pip install "./dist/paperrule-0.1.0-py3-none-any.whl" httpx
    .venv/bin/python -c "from pathlib import Path; Path('.test-tmp').mkdir(exist_ok=True)"
    .venv/bin/python scripts/wheel_smoke.py dist/paperrule-0.1.0-py3-none-any.whl --temporary-root .test-tmp

The smoke check installs the exact wheel into a disposable target and starts an isolated Python process outside the source checkout. It verifies the imported package location, the bundled homepage and referenced assets, API availability, and private-file isolation. It reuses the invoking interpreter's dependencies and reports that limitation explicitly. Full first-machine onboarding, real-provider evaluation, and the remaining acceptance scenarios require their own evidence.

## Troubleshooting

- Missing webpage: for source builds, run the frontend build before building the wheel. For an installed distribution, inspect the wheel and use the wheel smoke check.
- Installation rejects the dependency lock: use the committed package.json and package-lock.json together and npm ci. Do not silently upgrade dependencies.
- Missing PDF or DOCX parser: install the ingest extra in the same virtual environment as PaperRule.
- Records appear missing: check PAPERRULE_MEMORY before starting the application and select the directory used for initialization.
- Git push fails: approved local changes remain available. Check the configured private remote and connectivity; synchronization failure does not mean local approval was lost.
- AI is unavailable: keep editing proposals manually or configure a supported provider. Do not treat unavailable semantic review as a passed check.

See the [release checklist](release-checklist.md) for publication checks and the [project README](../README.md) for the product overview.
