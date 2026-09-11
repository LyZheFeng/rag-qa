# 人机一致性抽样(30 条)

> 来源:v0.2-hybrid 全量 run(v0.2-hybrid_20260910_215238),种子 7 可复现。
> **你的打分(1~5)**:对照参考答案给 RAG 答案打分;
> 无法回答题:RAG 拒答=5(拒得对),硬答了=1(不该答);可答题被拒答=1。
| 编号 | 类型 | 问题 | 参考答案 | RAG 答案(judge 分) | 你的打分 |
|---|---|---|---|---|---|
| 1 | fact | 现在推荐使用哪个包来替代 FastAPI 中已弃用的 WSGIMiddleware，导入方式有什么变化？ | 建议改用 a2wsgi 包。只要确保已安装 a2wsgi 包，并且从 a2wsgi 正确导入 WSGIMiddleware 即可，使用方式保持不变。 | 现在推荐使用 `a2wsgi` 包来替代已弃用的 `fastapi.middleware.wsgi` 中的 `WSGIMiddleware` [1]。导入方式的变化是从 `a2wsgi` 包中导入 `(judge:5) | |
| 2 | fact | 如果想以系统的方式学习 FastAPI，官方推荐的做法是什么？ | 阅读 [教程 - 用户指南](../tutorial/index.md) 的每一章节。 | 如果想以系统的方式学习 FastAPI，官方推荐的做法是阅读教程 - 用户指南的每一章节 [1]。(judge:5) | |
| 3 | fact | 如果 FastAPI 扩展无法自动检测项目入口，可以通过哪些方式手动指定入口点？ | 可以通过 `pyproject.toml` 中的 `[tool.fastapi]` 或 VS Code 设置项 `fastapi.entryPoint` 来指定 | 如果 FastAPI 扩展无法自动检测项目入口，可以通过 `pyproject.toml` 中的 `[tool.fastapi]` 或 VS Code 设置项 `fastapi.entryPoint`(judge:5) | |
| 4 | fact | 如何在 FastAPI 中配置路径操作，使其不出现在生成的 OpenAPI 文档中？ | 使用参数 `include_in_schema` 并将其设置为 `False`。示例代码：

```python
from fastapi import Fas | 使用参数 `include_in_schema` 并将其设置为 `False`，来从生成的 OpenAPI 方案中排除一个路径操作，这样它就会从自动化文档系统中排除掉 [2]。(judge:4) | |
| 5 | fact | 在 FastAPI 中，如果配置了前端静态文件目录，同时又定义了一个相同路径的路径操作函数，哪个优先级更高？ | 路径操作（Path Operation）优先。 | 在 FastAPI 中，路径操作函数的优先级更高。FastAPI 会先检查路径操作，只有在没有普通路由匹配时，才会检查前端文件，因此你的 API 不会受到影响 [4]。(judge:5) | |
| 6 | fact | 在 FastAPI 测试扩展示例中，假设 main.py 包含其他路径操作，其中 GET 和 POST 操作分别可能返回 | GET 操作可能返回一个错误，POST 操作可能返回多个错误。两个路径操作都需要一个 X-Token 头。 | 在 FastAPI 测试扩展示例中，假设 main.py 包含其他路径操作，其中 GET 操作可能返回一个错误，POST 操作可能返回多个错误，且这两个路径操作都需要一个 X-Token 请求头 [1(judge:5) | |
| 7 | fact | 如果前端运行在 http://localhost:8080 并尝试与默认端口的后端通信，后端需要如何配置才能允许该前端的 | 后端必须有一个「允许的源」列表，并且该列表必须包含 http://localhost:8080。 | 后端必须配置 CORS（跨域资源共享），因为 `http://localhost:8080` 和默认端口的后端（`http://localhost`）属于不同的源 [1][2]。后端需要有一个「允许的(judge:5) | |
| 8 | fact | FastAPI 推荐使用哪个库来与 SQL 数据库交互，该库通过什么机制简化代码？ | 推荐使用 SQLModel，它通过*数据模型*和*表模型*简化代码。 | FastAPI 推荐使用 SQLModel 来与 SQL 数据库交互 [1]。该库通过*数据模型*和*表模型*来简化代码 [1]。(judge:5) | |
| 9 | fact | 在 FastAPI 中使用 Python 的 dataclass 定义请求体时，如何声明一个可选的字符串字段和一个可选的 | 可以使用联合类型语法，将类型与 None 结合，例如：`description: str | None = None` 和 `tax: float | None | 【拒答】提供的资料中未包含使用 Python dataclass 定义请求体的具体说明或示例，资料主要介绍了使用 Pydantic 模型（BaseModel）声明请求体字段的方法，因此无法依据现有资料(judge:1) | |
| 10 | fact | 在 FastAPI 中，如果我希望路径操作根据业务逻辑返回不同的 HTTP 状态码（例如更新成功返回 200，创建新条目 | 通过直接返回一个 `Response` 对象（如 `JSONResponse`），并在其中设置 `status_code` 参数为你想要的值。 | 可以通过直接返回一个 `Response` 对象（例如 `JSONResponse`）来实现，并在其中直接设置 `status_code` 为你需要的值 [1]。(judge:5) | |
| 11 | fact | 在处理用户模型时，为什么通常需要将输入模型、输出模型和数据库模型分开定义？ | 因为输入模型应该含密码，输出模型不应含密码，而数据库模型可能需要包含哈希后的密码。 | 在处理用户模型时，通常需要将输入模型、输出模型和数据库模型分开定义，因为输入模型应该包含密码，输出模型不应包含密码，而数据库模型可能需要包含哈希后的密码 [1]。(judge:5) | |
| 12 | fact | 在 FastAPI 路径操作函数中，如何获取客户端的主机地址（Host）？ | 在路径操作函数中声明一个类型为 `Request` 的参数，然后通过 `request.client.host` 获取客户端主机地址。示例代码如下：

```p | 在 FastAPI 路径操作函数中，可以通过将参数类型声明为 `Request` 来直接访问请求对象，然后使用 `request.client.host` 获取客户端的主机地址 [1]。(judge:4) | |
| 13 | fact | 在 FastAPI 中，如果需要在 response_model 参数中使用联合类型，为什么不能直接用 `|` 符号，应 | 因为在 `response_model=` 等非类型注解的参数位置不能直接使用 `|` 符号，应使用 `typing` 中的 `Union` 来代替。例如：`U | 【拒答】资料中未提供关于在 `response_model` 参数中直接使用 `|` 符号联合类型的具体限制说明或推荐的替代方案（如 `Union` 的具体用法），仅说明了无效的返回类型注解（如 `R(judge:1) | |
| 14 | fact | 如果我想让查询参数在 URL 中显示为 item-query，但 Python 变量名必须是 item_query，应该 | 使用 `alias` 参数声明一个别名，FastAPI 会用该别名在 URL 中查找参数值。 | 应该使用 `alias` 参数来声明别名，FastAPI 会用该别名在 URL 中查找参数值 [1][4]。(judge:5) | |
| 15 | fact | 在 FastAPI 中，如果请求 URL 缺少一个必选的查询参数（例如 `needy`），服务器返回的错误响应中 `de | type 为 "missing"，msg 为 "Field required"。 | 在 FastAPI 中，如果请求 URL 缺少一个必选的查询参数（例如 `needy`），服务器返回的错误响应中 `detail` 列表里的 `type` 字段值为 "missing"，`msg` 字(judge:5) | |
| 16 | reas | 为什么 FastAPI 中严格的 Content-Type 检查带来的安全风险，在部署于开放互联网且已实施认证机制的应用 | 因为在开放互联网环境下，应用默认不信任网络，且对特权端点实施了认证防护，攻击者无法直接通过脚本绕过交互发送特权请求，因此该特定风险不适用。相反，在本地网络中，如 | 在部署于开放互联网的应用中，由于不会“信任网络”且不允许任何人不经认证就发送特权请求，攻击者通常需直接运行脚本发送请求，因此应用往往已对特权端点做好安全防护，该风险不适用 [1]。而在本地网络环境中，(judge:4) | |
| 17 | reas | 在定义请求体字段时，`Body` 和 `Field` 的导入来源有什么区别？如果混用会怎样？ | `Body` 需要从 `fastapi` 包导入，而 `Field` 必须直接从 `pydantic` 包导入。这是因为 `Field` 是 Pydantic  | 在定义请求体字段时，`Body` 是从 `fastapi` 导入的，而 `Field` 必须直接从 `pydantic` 导入 [3]。资料中未提供关于混用 `Body` 和 `Field` 会导致的(judge:3) | |
| 18 | reas | 在 FastAPI 生成的 OpenAPI 文档中，422 状态码与使用 $ref 指向 Item 模型的响应（如 20 | 本质区别在于引用的目标类型不同：422 状态码引用的是全局定义的通用验证错误模式（HTTPValidationError），用于标准化表示验证失败的结构；而使用 | 【拒答】提供的资料中未包含关于 422 状态码在 OpenAPI 文档中 Schema 引用的具体描述，也未提及 422 状态码与使用 $ref 指向模型的其他状态码（如 200 或 201）在引用机(judge:1) | |
| 19 | reas | 在 FastAPI 全栈模板的部署架构中，Traefik 除了承担反向代理和负载均衡的基础职责外，还通过什么机制简化了  | Traefik 通过配置前端代理来自动处理 HTTPS 证书。这意味着开发者无需手动申请、配置或续期 SSL/TLS 证书，Traefik 会在反向代理层面自动 | 在 FastAPI 全栈模板的部署架构中，Traefik 通过自动处理 HTTPS 证书的机制简化了运维工作 [4]。此外，资料指出 Traefik 也可以处理证书更新 [3]。(judge:4) | |
| 20 | reas | 为什么 FastAPI 的测试客户端在 API 设计风格上与 Requests 库保持高度一致，这背后是基于怎样的技术依 | 因为 FastAPI 的测试客户端（Starlette TestClient）底层是基于 HTTPX 构建的，而 HTTPX 本身又是基于 Requests 库 | FastAPI 的测试客户端（TestClient）基于 HTTPX 构建，而 HTTPX 又是基于 Requests 设计的，因此它们在 API 设计风格上保持高度一致且易于理解 [3]。这种技术依(judge:5) | |
| 21 | reas | 在 FastAPI 的 Lifespan 机制中，异步上下文管理器是如何利用 `yield` 关键字来区分应用启动和关闭 | 异步上下文管理器通过 `yield` 将逻辑分为两部分：`yield` 之前的代码在应用启动（进入 `async with` 块）时执行，而 `yield` 之 | 在 FastAPI 的 Lifespan 机制中，异步上下文管理器通过 `yield` 关键字来区分启动和关闭逻辑：执行 `yield` 之前的代码用于处理应用启动时的逻辑，而执行 `yield` 之(judge:4) | |
| 22 | reas | 在 FastAPI 中，如果返回的数据不符合定义的返回模型（例如缺少字段），系统会返回数据错误还是服务器错误？这种设计对 | 系统会返回服务器错误（Server Error）。这种设计的好处在于，它向客户端保证了接收到的数据结构和内容是完全符合预期的；如果数据无效，说明是后端代码逻辑有 | 如果返回的数据无效（例如缺少某个字段），FastAPI 将返回服务器错误而不是返回错误的数据 [1]。这种设计的好处是确保你和你的客户端都可以确定会收到期望的数据及其结构 [1]。(judge:4) | |
| 23 | reas | 在 FastAPI 中，为什么建议通过定义基类（如 UserBase）来复用模型属性，而不是直接在每个模型中重复声明相同 | 建议通过定义基类来复用模型属性，主要是为了避免代码重复带来的隐患。如果直接重复声明，会导致代码失步（即更新了一处代码但未同步更新其他位置），进而引发 bug 和 | 在 FastAPI 中，建议通过定义基类（如 UserBase）来复用模型属性，是因为代码重复会导致 bug、安全问题以及代码失步等问题（例如更新了某个位置的代码，但没有同步更新其它位置的代码）[1](judge:4) | |
| 24 | reas | 在 FastAPI 项目中，如果直接使用标准的 Python `dataclasses` 模块导致自动生成的 API 文 | 应该将标准的 `dataclasses` 替换为 `pydantic.dataclasses`。这种替换不会影响代码兼容性，因为 `pydantic.datac | 如果直接使用标准的 Python `dataclasses` 模块导致自动生成的 API 文档出现错误，可以将标准的 `dataclasses` 替换为 `pydantic.dataclasses` (judge:5) | |
| 25 | unan | 在将 FastAPI 从 0.100.0 升级到 0.104.0 时，Pydantic v2 中关于 `model_va | *(语料无答案,正确行为是拒答)* | 【拒答】资料中未包含关于 `model_validate` 弃用警告的具体处理建议，也未提供针对旧版本 Pydantic v1 兼容层移除的具体时间表，仅提及 FastAPI 0.128.0 移除了对(judge:None) | |
| 26 | unan | 在 FastAPI 中如何集成 Celery 以处理耗时的异步后台任务，并获取任务执行进度？ | *(语料无答案,正确行为是拒答)* | 【拒答】资料中仅提到如果需要执行繁重的后台计算且不需要由同一进程运行，可以使用 Celery 等更大的工具，并指出它们往往需要更复杂的配置（如 RabbitMQ 或 Redis），但资料未提供如何集成(judge:None) | |
| 27 | unan | 在 Nginx 反向代理配置中，如何正确设置 proxy_set_header X-Forwarded-Proto 以支 | *(语料无答案,正确行为是拒答)* | 【拒答】提供的资料中未包含 Nginx 反向代理的具体配置代码或 `proxy_set_header` 的设置方法，仅说明了 FastAPI 应用服务器需通过 `--forwarded-ips` 选项(judge:None) | |
| 28 | unan | 在 FastAPI 应用中，如何集成 OpenTelemetry 以实现分布式链路追踪（Tracing），并自动记录每个 | *(语料无答案,正确行为是拒答)* | 【拒答】提供的资料中未包含关于在 FastAPI 中集成 OpenTelemetry 实现分布式链路追踪或记录 Trace ID 和 Span ID 的信息。(judge:None) | |
| 29 | unan | 在将项目从 FastAPI 0.95.x 升级到 0.100.0 时，除了 Pydantic V2 的迁移外，还有哪些被 | *(语料无答案,正确行为是拒答)* | 【拒答】提供的资料仅涉及从 Pydantic v1 迁移到 Pydantic v2 的版本支持情况（如 FastAPI 0.100.0 同时支持 Pydantic v1 和 v2），未包含 FastA(judge:None) | |
| 30 | unan | 在 FastAPI 中如何配置基于 Redis 的全局限流中间件，以限制特定 IP 地址每秒的最大请求数为 100？ | *(语料无答案,正确行为是拒答)* | 【拒答】提供的资料中仅介绍了 FastAPI 中间件的基本概念、CORSMiddleware 的使用以及高级中间件的章节索引，未包含关于基于 Redis 的全局限流中间件的具体实现或配置方法，因此无法(judge:None) | |